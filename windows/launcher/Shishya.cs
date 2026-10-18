// Shishya.exe — starts Shishya.
//
// The program itself is Python: the panel, the sandbox control and the
// clone's apps are all the same source as the Mac build. What a Windows
// person double-clicks should still be a program with Shishya's name and
// icon, that pins to the taskbar and shows in Start — so this is that
// program, and all it does is start the bundled runtime on shishya_win.pyw
// and get out of the way. No console window, no terminal, nothing to install
// first.
//
// Compiled with the C# compiler every Windows has (.NET Framework 4), by
// windows\build.ps1. Kept this small on purpose: anything clever belongs in
// the Python, where it is the same code on every platform.

using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Windows.Forms;

[assembly: System.Reflection.AssemblyTitle("Shishya")]
[assembly: System.Reflection.AssemblyProduct("Shishya")]
[assembly: System.Reflection.AssemblyDescription("An apprentice that learns a job by watching you do it once")]
[assembly: System.Reflection.AssemblyCompany("Shishya")]
[assembly: System.Reflection.AssemblyVersion("1.0.0.0")]
[assembly: System.Reflection.AssemblyFileVersion("1.0.0.0")]

static class Launcher
{
    [STAThread]
    static int Main(string[] args)
    {
        string home = AppDomain.CurrentDomain.BaseDirectory;
        string pythonw = Path.Combine(home, "runtime", "pythonw.exe");
        string entry = Path.Combine(home, "shishya_win.pyw");
        if (!File.Exists(pythonw) || !File.Exists(entry))
        {
            MessageBox.Show("Shishya is incomplete — its runtime folder is missing.\n\n" +
                            "Reinstall Shishya to repair it.", "Shishya",
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        var start = new ProcessStartInfo(pythonw)
        {
            Arguments = "-I \"" + entry + "\" " +
                        string.Join(" ", args.Select(a => "\"" + a.Replace("\"", "\\\"") + "\"")),
            WorkingDirectory = home,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        // -I: isolated mode. A PYTHONPATH or a user site-packages on this
        // machine must not be able to put its own code in front of ours.
        start.EnvironmentVariables.Remove("PYTHONPATH");
        start.EnvironmentVariables.Remove("PYTHONHOME");
        Process.Start(start);
        return 0;
    }
}
