using System;
using System.Collections.Generic;
namespace PolyBridge;
public static partial class Api
{
    static void QuitToMenu()
    {
        try { if (ResultScreen.IsShowing()) ResultScreen.Hide(); } catch (Exception e) { Plugin.L.LogWarning("ResultScreen.Hide: " + e.Message); }
        GameManager.ReturnToMenu();
        Loading = false;
    }
}
