$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$out  = Join-Path $root "FrogModEditor.exe"

# ── C# source ──────────────────────────────────────────────
# Single-quoted here-string: nothing is escaped, C# gets exact text.
# Assembly metadata makes the PE look like a real application so AV
# heuristics don't flag it as a suspicious script-compiled binary.
$cs = @'
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("Frog Mod Editor")]
[assembly: AssemblyDescription("Launcher for the Frog Mod Editor (Motor Town modding tool)")]
[assembly: AssemblyCompany("Cryovac")]
[assembly: AssemblyProduct("FrogModEditor")]
[assembly: AssemblyCopyright("Copyright (c) 2025 Cryovac")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

class FrogLauncher {
    [STAThread]
    static void Main() {
        try {
            string dir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            string pythonw = Path.Combine(dir, "source", "python", "pythonw.exe");
            string pythonExe = Path.Combine(dir, "source", "python", "python.exe");
            string app = Path.Combine(dir, "source", "src", "native_qt_app.py");
            string cwd = Path.Combine(dir, "source", "src");

            if (!File.Exists(app)) {
                MessageBox.Show(
                    "Could not find:\n" + app + "\n\nMake sure FrogModEditor.exe is next to the 'source' folder.",
                    "Frog Mod Editor", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            string runtime = File.Exists(pythonw) ? pythonw : pythonExe;
            if (!File.Exists(runtime)) {
                MessageBox.Show(
                    "Python runtime not found.\n\nExtract the Runtime Overlay into source\\python\\.",
                    "Frog Mod Editor", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = runtime;
            char q = '"';
            psi.Arguments = q + app + q;
            psi.WorkingDirectory = cwd;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            Process.Start(psi);
        } catch (Exception ex) {
            MessageBox.Show("Launch failed:\n" + ex.Message,
                "Frog Mod Editor", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
'@

Write-Host "Compiling FrogModEditor.exe..."

# Remove old exe if present (Add-Type won't overwrite)
if (Test-Path $out) { Remove-Item $out -Force }

Add-Type -TypeDefinition $cs `
    -ReferencedAssemblies System.Windows.Forms `
    -OutputType WindowsApplication `
    -OutputAssembly $out

if (Test-Path $out) {
    Write-Host ""
    Write-Host "SUCCESS: FrogModEditor.exe created!" -ForegroundColor Green
    Write-Host "Double-click it to launch the editor."
    Write-Host ""
    Write-Host "NOTE: If your antivirus flags this file, add an exclusion for it."
    Write-Host "      The source code is in source\build_launcher.ps1 - nothing malicious."
} else {
    Write-Host "Build failed." -ForegroundColor Red
    exit 1
}
