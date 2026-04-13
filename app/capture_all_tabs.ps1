Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

Add-Type -ReferencedAssemblies System.Drawing @"
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
public class WC3 {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBlt, uint nFlags);
    [DllImport("user32.dll")] public static extern void SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, int dwExtraInfo);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    public static int[] GetRect(IntPtr hwnd) {
        RECT r; GetWindowRect(hwnd, out r);
        return new int[] { r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top };
    }
    public static void Capture(IntPtr hwnd, string path) {
        RECT r; GetWindowRect(hwnd, out r);
        int w = r.Right - r.Left; int h = r.Bottom - r.Top;
        Bitmap bmp = new Bitmap(w, h, PixelFormat.Format32bppArgb);
        Graphics g = Graphics.FromImage(bmp);
        IntPtr hdc = g.GetHdc();
        PrintWindow(hwnd, hdc, 2);
        g.ReleaseHdc(hdc);
        g.Dispose();
        bmp.Save(path, ImageFormat.Png);
        bmp.Dispose();
    }
    public static void Click(int x, int y) {
        SetCursorPos(x, y);
        System.Threading.Thread.Sleep(200);
        mouse_event(0x0002, 0, 0, 0, 0);
        System.Threading.Thread.Sleep(50);
        mouse_event(0x0004, 0, 0, 0, 0);
    }
}
"@

$dir = "C:\Users\akoti\University RP3 - Composite Failure Surrogate Modelling\rp3-app\screenshots\tauri"
$proc = Get-Process | Where-Object { $_.MainWindowTitle -like "*RP3*" -or $_.MainWindowTitle -like "*Composite*" } | Select-Object -First 1
if (-not $proc) { Write-Host "ERROR: no RP3 window"; exit 1 }
$hwnd = $proc.MainWindowHandle

# First restore to a known window size (not maximized, to avoid DPI issues)
[WC3]::ShowWindow($hwnd, 9) | Out-Null  # RESTORE
Start-Sleep -Milliseconds 500

# Set to a specific size and position using MoveWindow
Add-Type @"
using System; using System.Runtime.InteropServices;
public class MW { [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint); }
"@
# Place at (0,0) with size 1280x800 in screen pixels
[MW]::MoveWindow($hwnd, 0, 0, 1280, 800, $true) | Out-Null
Start-Sleep -Milliseconds 500

[WC3]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 500

$r = [WC3]::GetRect($hwnd)
$wx = $r[0]; $wy = $r[1]; $ww = $r[2]; $wh = $r[3]
Write-Host "Window: ($wx,$wy) ${ww}x${wh}"

function Snap($name) {
    Start-Sleep -Milliseconds 1200
    [WC3]::Capture($hwnd, "$dir\$name.png")
    Write-Host "  >> $name"
}

# Capture initial state to find exact element positions
Snap "00_reference"
Write-Host "Reference screenshot saved. Check element positions."

# Based on 1280x800 window, estimate tab positions
# With DPI 150%, CSS viewport is ~853x533
# Title bar ~30px screen, after that CSS starts
# Header h-12 = 48px CSS = 72px screen -> top at 30, bottom at 102
# Tab bar h-9 = 36px CSS = 54px screen -> top at 102, bottom at 156
# Tab text center ~ 102 + 27 = 129

$tabY = 129

# Tab text positions (CSS px * 1.5, center of text):
# Analysis: starts ~16px, width ~100px -> center 66*1.5=99
# Stress Field: ~116px, width ~120px -> center 176*1.5=264
# Laminate: ~236px, width ~100px -> center 286*1.5=429
# Explorer: ~336px, width ~100px -> center 386*1.5=579
# Project: ~436px, width ~100px -> center 486*1.5=729

# But these are from window left edge, so add $wx
$tabs = @{
    "analysis" = $wx + 99
    "stress" = $wx + 264
    "laminate" = $wx + 429
    "explorer" = $wx + 579
    "project" = $wx + 729
}
$tabBarY = $wy + $tabY

# Header Run button and Presets: right side of header
# Run Enter button ~ CSS 880px from left = 880*1.5 = 1320px from window left
# But window is 1280px, so it should be at ~CSS 830px -> 830*1.5=1245
# Run button center Y: title bar + header center = 30 + 36 = 66
$runX = $wx + 1100
$runY = $wy + 55

Write-Host "Tab Y = $tabBarY"
Write-Host "Tab positions: Analysis=$($tabs.analysis), Stress=$($tabs.stress), Lam=$($tabs.laminate), Exp=$($tabs.explorer), Proj=$($tabs.project)"
Write-Host "Run button: ($runX, $runY)"

# 0. Initial
Snap "01_analysis_init"

# 1. Try pressing Enter to trigger prediction (since Run is keyboard shortcut)
Write-Host "Sending Enter key for prediction..."
[WC3]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 200
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Start-Sleep -Milliseconds 5000
Snap "02_analysis_predicted"

# 2. Click Stress Field tab
Write-Host "Clicking Stress Field tab..."
[WC3]::Click($tabs.stress, $tabBarY)
Snap "03_stress_field"

# 3. Laminate
Write-Host "Clicking Laminate tab..."
[WC3]::Click($tabs.laminate, $tabBarY)
Snap "04_laminate"

# 4. Explorer
Write-Host "Clicking Explorer tab..."
[WC3]::Click($tabs.explorer, $tabBarY)
Snap "05_explorer"

# 5. Project
Write-Host "Clicking Project tab..."
[WC3]::Click($tabs.project, $tabBarY)
Snap "06_project"

# 6. Back to Analysis
Write-Host "Back to Analysis..."
[WC3]::Click($tabs.analysis, $tabBarY)
Snap "07_analysis_final"

Write-Host "`nDone."
