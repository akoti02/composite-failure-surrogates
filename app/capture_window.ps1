Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

Add-Type -ReferencedAssemblies System.Drawing @"
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
public class WinCapture {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBlt, uint nFlags);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }

    public static void Capture(IntPtr hwnd, string path) {
        RECT rect;
        GetWindowRect(hwnd, out rect);
        int w = rect.Right - rect.Left;
        int h = rect.Bottom - rect.Top;
        if (w <= 0 || h <= 0) return;

        Bitmap bmp = new Bitmap(w, h, PixelFormat.Format32bppArgb);
        Graphics g = Graphics.FromImage(bmp);
        IntPtr hdc = g.GetHdc();
        PrintWindow(hwnd, hdc, 2);
        g.ReleaseHdc(hdc);
        g.Dispose();
        bmp.Save(path, ImageFormat.Png);
        bmp.Dispose();
        Console.WriteLine("OK " + w + "x" + h);
    }
}
"@

$proc = Get-Process | Where-Object { $_.MainWindowTitle -like "*RP3*" -or $_.MainWindowTitle -like "*Composite*" } | Select-Object -First 1
if (-not $proc) { Write-Host "ERROR: no RP3 window"; exit 1 }

$hwnd = $proc.MainWindowHandle
[WinCapture]::ShowWindow($hwnd, 9) | Out-Null
Start-Sleep -Milliseconds 200
[WinCapture]::ShowWindow($hwnd, 3) | Out-Null
Start-Sleep -Milliseconds 500
[WinCapture]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 1000

[WinCapture]::Capture($hwnd, "C:\Users\akoti\University RP3 - Composite Failure Surrogate Modelling\rp3-app\screenshots\tauri\01_tauri_live.png")
