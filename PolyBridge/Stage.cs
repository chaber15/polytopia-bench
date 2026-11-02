using System;
using System.Collections.Generic;
using System.Text.Json;
using Polytopia.Data;
using PolytopiaBackendBase.Common;
using PolytopiaBackendBase.Game;

namespace PolyBridge;

// Dev tool for pictures, not used in benchmark play: POST /stage {"state": <a logged turn_start state>, "tribes": {"1": "Imperius", ...}}
// rewrites the loaded game's map, cities, units and the local player's fog to match the logged state, then reloads the
// game from that state so the game draws it. Start any single-player game of the same map size first.
public static partial class Api
{
    // POST /camera {"zoom": z, "hideUI": true}: zooms the camera (centred on the map) and hides the screen UI, for screenshots.
    static Reply Camera(Request r)
    {
        var cam = CameraController.Instance;
        if (cam == null) return Reply.Err("no camera", 409);
        if (r.HasBody && r.Body.TryGetProperty("hideUI", out var hu))
        {
            int n = 0;
            foreach (var o in UnityEngine.Object.FindObjectsOfType(Il2CppInterop.Runtime.Il2CppType.Of<UnityEngine.Canvas>()))
            {
                var c = o.TryCast<UnityEngine.Canvas>();
                if (c != null && c.renderMode != UnityEngine.RenderMode.WorldSpace) { c.enabled = !hu.GetBoolean(); n++; }
            }
            events.Add($"canvases {(hu.GetBoolean() ? "hidden" : "shown")}: {n}");
        }
        if (r.HasBody && r.Body.TryGetProperty("zoom", out var z))
        {
            cam.CenterCamera();
            cam.SetCameraZoom((float)z.GetDouble());
        }
        return Reply.Ok(new Dictionary<string, object> { ["ok"] = true, ["zoom"] = CameraController.CurrentZoom, ["normalized"] = CameraController.NormalizedZoom, ["events"] = DrainEvents() });
    }

    static Reply Stage(Request r)
    {
        var gs = Gs();
        if (gs == null) return Reply.Err("stage needs a loaded game", 409);
        if (!r.HasBody || !r.Body.TryGetProperty("state", out var st)) return Reply.Err("body needs state", 400);
        var map = st.GetProperty("map");
        int w = map.GetProperty("w").GetInt32(), h = map.GetProperty("h").GetInt32();
        if (w != gs.Map.Width || h != gs.Map.Height) return Reply.Err($"map is {gs.Map.Width}x{gs.Map.Height}, state is {w}x{h}", 409);
        byte me = GameManager.LocalPlayer.Id;
        var tiles = gs.Map.Tiles;
        TileData At(JsonElement xy) => tiles[xy[1].GetInt32() * w + xy[0].GetInt32()];

        // players: tribes, scores, knocked-out flags
        if (r.Body.TryGetProperty("tribes", out var tr))
            foreach (var p in tr.EnumerateObject())
                if (gs.TryGetPlayer(byte.Parse(p.Name), out var ps) && Enum.TryParse<TribeType>(p.Value.GetString(), true, out var tt)) ps.tribe = tt;
        int turn = st.GetProperty("turn").GetInt32();
        if (gs.TryGetPlayer(me, out var mine)) mine.score = (uint)st.GetProperty("me").GetProperty("score").GetInt64();
        if (st.TryGetProperty("opponents", out var opps))
            foreach (var o in opps.EnumerateArray())
                if (gs.TryGetPlayer((byte)o.GetProperty("id").GetInt32(), out var op))
                {
                    op.score = (uint)o.GetProperty("score").GetInt64();
                    if (o.TryGetProperty("out", out var ko) && ko.GetBoolean()) op.killedTurn = (uint)turn;
                }

        // clear the map: no units, no improvements, nothing explored by us
        for (int i = 0; i < tiles.Length; i++)
        {
            var t = tiles[i];
            t.SetUnit(null);
            t.SetImprovement(null);
            t.SetResource(null);
            t.capitalOf = 0;
            t.owner = 0;
            t.hasRoad = false;
            t.SetExplored(me, false);
        }
        // tiles the model had seen
        foreach (var d in map.GetProperty("tiles").EnumerateArray())
        {
            var t = At(d.GetProperty("xy"));
            t.SetExplored(me, true);
            if (Enum.TryParse<TerrainData.Type>(d.GetProperty("t").GetString(), out var ter)) t.terrain = ter;
            if (d.TryGetProperty("own", out var own)) t.owner = (byte)own.GetInt32();
            // climate (which tribe's look the tile has): the original owner's tribe, worked out by the caller from the whole log
            if (d.TryGetProperty("clim", out var cl) && Enum.TryParse<TribeType>(cl.GetString(), true, out var ct)) t.climate = ct;
            if (d.TryGetProperty("road", out var rd) && rd.GetBoolean()) t.hasRoad = true;
            if (d.TryGetProperty("res", out var res) && Enum.TryParse<ResourceData.Type>(res.GetString(), out var rt))
                t.SetResource(new ResourceState { type = rt });
            if (d.TryGetProperty("imp", out var imp) && Enum.TryParse<ImprovementData.Type>(imp.GetString(), out var it))
                t.SetImprovement(new ImprovementState { type = it, level = 1 });
        }
        var cityAt = new List<(int x, int y, byte own)>();
        if (st.TryGetProperty("cities", out var cities))
            foreach (var c in cities.EnumerateArray())
            {
                var t = At(c.GetProperty("xy"));
                byte own = (byte)c.GetProperty("own").GetInt32();
                var city = new ImprovementState { type = ImprovementData.Type.City, level = (ushort)c.GetProperty("lvl").GetInt32(), founder = own };
                if (c.TryGetProperty("name", out var nm)) city.name = nm.GetString();
                if (c.TryGetProperty("pop", out var pop)) city.population = (short)pop.GetInt32();
                t.SetImprovement(city);
                t.owner = own;
                if (c.TryGetProperty("cap", out var cap) && cap.GetBoolean()) t.capitalOf = own;
                cityAt.Add((t.coordinates.X, t.coordinates.Y, own));
            }
        foreach (var key in new[] { "villages", "ruins" })
            if (st.TryGetProperty(key, out var list))
                foreach (var xy in list.EnumerateArray())
                    At(xy).SetImprovement(new ImprovementState { type = key == "villages" ? ImprovementData.Type.City : ImprovementData.Type.Ruin, level = 1 });
        // territory belongs to the nearest city of the same owner
        for (int i = 0; i < tiles.Length; i++)
        {
            var t = tiles[i];
            if (t.owner == 0) continue;
            int best = int.MaxValue;
            foreach (var (x, y, o) in cityAt)
            {
                if (o != t.owner) continue;
                int dd = Math.Max(Math.Abs(x - t.coordinates.X), Math.Abs(y - t.coordinates.Y));
                if (dd < best) { best = dd; t.rulingCityCoordinates = new WorldCoordinates(x, y); }
            }
        }
        // units
        int units = 0;
        if (st.TryGetProperty("units", out var us))
            foreach (var u in us.EnumerateArray())
            {
                if (!Enum.TryParse<UnitData.Type>(u.GetProperty("type").GetString(), out var ut)) { events.Add("stage: unknown unit " + u.GetProperty("type").GetString()); continue; }
                var t = At(u.GetProperty("xy"));
                var s = new UnitState
                {
                    id = (uint)u.GetProperty("id").GetInt64(),
                    owner = (byte)u.GetProperty("own").GetInt32(),
                    type = ut,
                    coordinates = t.coordinates,
                    home = t.coordinates,
                    health = (ushort)Math.Round(u.GetProperty("hp").GetDouble() * 10),
                    promotionLevel = (ushort)(u.TryGetProperty("vet", out var v) && v.GetBoolean() ? 1 : 0),
                    effects = new Il2CppSystem.Collections.Generic.List<UnitEffect>(),
                };
                t.SetUnit(s);
                units++;
            }
        gs.CurrentTurn = (uint)turn;

        var bytes = SerializationHelpers.ToByteArray(gs, gs.Version);
        Plugin.L.LogInfo($"stage: turn {turn}, {cityAt.Count} cities, {units} units, {bytes.Length} bytes; reloading");
        QuitToMenu();
        int phase = 0, frames = 0;
        return new Reply
        {
            Poll = () =>
            {
                frames++;
                if (phase == 0)
                {
                    if (Gs() != null || frames < 60) return null;
                    Loading = true;
                    GameManager.Instance.SetLocalClient();
                    var res = GameManager.Client.CreateSession(bytes, Il2CppSystem.Guid.NewGuid());
                    if (res != CreateSessionResult.Success) { Loading = false; return PJson.Write(new Dictionary<string, object> { ["ok"] = false, ["error"] = "CreateSession " + res }); }
                    GameManager.Instance.LoadLevel();
                    phase = 1; frames = 0;
                    return null;
                }
                if (Gs() == null || frames < 240) return null;
                Loading = false;
                return PJson.Write(new Dictionary<string, object> { ["ok"] = true, ["turn"] = turn, ["cities"] = cityAt.Count, ["units"] = units, ["events"] = DrainEvents() });
            }
        };
    }
}
