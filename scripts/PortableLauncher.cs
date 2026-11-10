using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;
using System.Web.Script.Serialization;
using System.Collections.Generic;

class PortableLauncher {
    [STAThread]
    static void Main() {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(root, "runtime", "python", "pythonw.exe");
        string script = Path.Combine(root, "scripts", "portable_launch.py");
#if STOP
        try {
            string statePath = Path.Combine(root, "user-data", "instance.json");
            if (!File.Exists(statePath)) return;
            var state = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(statePath));
            using (Process service = Process.GetProcessById(Convert.ToInt32(state["pid"]))) {
                string executable = service.MainModule.FileName;
                if (service.HasExited || !String.Equals(Path.GetDirectoryName(executable), Path.GetDirectoryName(python), StringComparison.OrdinalIgnoreCase)) return;
                ProcessStartInfo stop = new ProcessStartInfo("taskkill.exe", "/PID " + service.Id + " /T /F");
                stop.UseShellExecute = false;
                stop.CreateNoWindow = true;
                using (Process command = Process.Start(stop)) command.WaitForExit();
            }
        } catch (ArgumentException) { }
          catch (Exception e) { MessageBox.Show(e.Message, "策略拾录停止服务"); }
        return;
#else
        if (!File.Exists(python)) {
            MessageBox.Show("请先完整解压软件包，再双击启动。", "策略拾录");
            return;
        }
        try {
            ProcessStartInfo info = new ProcessStartInfo(python, "\"" + script + "\"");
            info.WorkingDirectory = root;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            Process.Start(info);
        } catch (Exception e) {
            MessageBox.Show(e.Message, "策略拾录启动失败");
        }
#endif
    }
}
