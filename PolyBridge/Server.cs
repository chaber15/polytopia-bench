using System;
using System.Collections;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Threading;

namespace PolyBridge;

// Result of handling a request on the main thread: either an immediate answer or a poller that returns
// the JSON body once the game is ready again (null while still waiting).
public class Reply
{
    public int Status = 200;
    public string Json;
    public Func<string> Poll;
    public static Reply Ok(object o) => new Reply { Json = PJson.Write(o) };
    public static Reply Err(string error, int status = 200, Dictionary<string, object> extra = null)
    {
        var d = new Dictionary<string, object> { ["ok"] = false, ["error"] = error };
        if (extra != null) foreach (var kv in extra) d[kv.Key] = kv.Value;
        return new Reply { Status = status, Json = PJson.Write(d) };
    }
}

public class Request
{
    public string Method, Path;
    public Dictionary<string, string> Query = new();
    public JsonElement Body;          // ValueKind Undefined when empty
    public bool HasBody;
    public int IntQuery(string k, int def) => Query.TryGetValue(k, out var v) && int.TryParse(v, out var i) ? i : def;
}

class Job
{
    public Request Req;
    public Reply Reply;
    public Func<string> Poll;
    public DateTime Deadline;
    public ManualResetEventSlim Done = new(false);
    public bool Started;
}

// HttpListener on a background thread; requests are queued and run on Unity's main thread via Pump().
public static class Http
{
    static HttpListener listener;
    static readonly ConcurrentQueue<Job> queue = new();
    static readonly List<Job> pending = new();
    public static Func<Request, Reply> Handler;
    public static int DefaultTimeout = 120;

    public static void Start(int port)
    {
        listener = new HttpListener();
        listener.Prefixes.Add($"http://localhost:{port}/");
        listener.Start();
        new Thread(Loop) { IsBackground = true, Name = "PolyBridge-http" }.Start();
        Plugin.L.LogInfo($"PolyBridge HTTP listening on {port}");
    }

    static void Loop()
    {
        while (listener.IsListening)
        {
            HttpListenerContext ctx;
            try { ctx = listener.GetContext(); } catch { return; }
            var c = ctx;
            new Thread(() => Serve(c)) { IsBackground = true }.Start();
        }
    }

    static void Serve(HttpListenerContext ctx)
    {
        string json; int status = 200;
        try
        {
            var req = new Request { Method = ctx.Request.HttpMethod, Path = ctx.Request.Url.AbsolutePath.TrimEnd('/') };
            var qs = ctx.Request.QueryString;
            foreach (var k in qs.AllKeys) if (k != null) req.Query[k] = qs[k];
            string body;
            using (var r = new StreamReader(ctx.Request.InputStream, Encoding.UTF8)) body = r.ReadToEnd();
            if (!string.IsNullOrWhiteSpace(body))
            {
                try { req.Body = JsonDocument.Parse(body).RootElement.Clone(); req.HasBody = true; }
                catch { Write(ctx, 400, "{\"ok\":false,\"error\":\"bad json\"}"); return; }
            }
            var job = new Job { Req = req, Deadline = DateTime.UtcNow.AddSeconds(req.IntQuery("timeout", DefaultTimeout)) };
            queue.Enqueue(job);
            if (!job.Done.Wait(TimeSpan.FromSeconds(req.IntQuery("timeout", DefaultTimeout) + 10)))
            { json = "{\"ok\":false,\"error\":\"main thread unresponsive\"}"; }
            else { json = job.Reply.Json; status = job.Reply.Status; }
        }
        catch (Exception e) { json = PJson.Write(new Dictionary<string, object> { ["ok"] = false, ["error"] = e.GetType().Name + ": " + e.Message }); }
        Write(ctx, status, json);
    }

    static void Write(HttpListenerContext ctx, int status, string json)
    {
        try
        {
            var bytes = Encoding.UTF8.GetBytes(json);
            ctx.Response.StatusCode = status;
            ctx.Response.ContentType = "application/json; charset=utf-8";
            ctx.Response.ContentLength64 = bytes.Length;
            ctx.Response.OutputStream.Write(bytes, 0, bytes.Length);
            ctx.Response.Close();
        }
        catch { }
    }

    // Called every frame from Update on the main thread.
    public static void Pump()
    {
        while (queue.TryDequeue(out var job))
        {
            try
            {
                var rep = Handler(job.Req);
                if (rep.Poll != null) { job.Poll = rep.Poll; pending.Add(job); }
                else { job.Reply = rep; job.Done.Set(); }
            }
            catch (Exception e)
            {
                Plugin.L.LogError(e.ToString());
                job.Reply = Reply.Err(e.GetType().Name + ": " + e.Message);
                job.Done.Set();
            }
        }
        for (int i = pending.Count - 1; i >= 0; i--)
        {
            var job = pending[i];
            string res = null;
            try { res = job.Poll(); }
            catch (Exception e) { res = PJson.Write(new Dictionary<string, object> { ["ok"] = false, ["error"] = e.GetType().Name + ": " + e.Message }); Plugin.L.LogError(e.ToString()); }
            if (res == null && DateTime.UtcNow > job.Deadline) res = "{\"ok\":false,\"error\":\"timeout\"}";
            if (res != null) { job.Reply = new Reply { Json = res }; pending.RemoveAt(i); job.Done.Set(); }
        }
    }
}

// Minimal JSON writer: Dictionary<string,object>, IEnumerable, primitives, strings. Compact output.
public static class PJson
{
    public static string Write(object o) { var sb = new StringBuilder(); W(sb, o); return sb.ToString(); }

    static void W(StringBuilder sb, object o)
    {
        switch (o)
        {
            case null: sb.Append("null"); break;
            case string s: Str(sb, s); break;
            case bool b: sb.Append(b ? "true" : "false"); break;
            case float f: sb.Append(f.ToString("0.##", System.Globalization.CultureInfo.InvariantCulture)); break;
            case double d: sb.Append(d.ToString("0.##", System.Globalization.CultureInfo.InvariantCulture)); break;
            case IDictionary<string, object> dict:
                sb.Append('{'); bool first = true;
                foreach (var kv in dict) { if (!first) sb.Append(','); first = false; Str(sb, kv.Key); sb.Append(':'); W(sb, kv.Value); }
                sb.Append('}'); break;
            case IEnumerable en when !(o is string):
                sb.Append('['); bool f2 = true;
                foreach (var x in en) { if (!f2) sb.Append(','); f2 = false; W(sb, x); }
                sb.Append(']'); break;
            case IFormattable fm: sb.Append(fm.ToString(null, System.Globalization.CultureInfo.InvariantCulture)); break;
            default: Str(sb, o.ToString()); break;
        }
    }

    static void Str(StringBuilder sb, string s)
    {
        sb.Append('"');
        foreach (var c in s)
        {
            switch (c)
            {
                case '"': sb.Append("\\\""); break;
                case '\\': sb.Append("\\\\"); break;
                case '\n': sb.Append("\\n"); break;
                case '\r': break;
                case '\t': sb.Append("\\t"); break;
                default: if (c < 0x20) sb.Append("\\u" + ((int)c).ToString("x4")); else sb.Append(c); break;
            }
        }
        sb.Append('"');
    }
}
