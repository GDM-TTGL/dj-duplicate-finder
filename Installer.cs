using System;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Windows.Forms;
using Microsoft.Win32;
using System.Diagnostics;

internal static class SetupApp
{
    [STAThread]
    private static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new SetupForm());
    }
}

internal sealed class SetupForm : Form
{
    private TextBox folder;
    private CheckBox desktopIcon;
    private ProgressBar progress;
    private Label status;
    private Button install;
    private bool busy;

    public SetupForm()
    {
        Text = "Instalar DJ Duplicate Finder v3";
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        ClientSize = new Size(570, 265);
        Font = new Font("Segoe UI", 9F);

        Label title = new Label();
        title.Text = "DJ Duplicate Finder v3";
        title.Font = new Font("Segoe UI", 18F, FontStyle.Bold);
        title.SetBounds(24, 18, 520, 36);
        Controls.Add(title);

        Label description = new Label();
        description.Text = "Instala el buscador de coincidencias de audio. No requiere instalar Python ni FFmpeg.";
        description.SetBounds(26, 62, 520, 38);
        Controls.Add(description);

        Label location = new Label();
        location.Text = "Carpeta de instalación:";
        location.SetBounds(26, 111, 200, 22);
        Controls.Add(location);

        folder = new TextBox();
        string testInstall = Environment.GetEnvironmentVariable("DJDF_TEST_INSTALL_DIR");
        folder.Text = !String.IsNullOrEmpty(testInstall) ? testInstall : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "DJ Duplicate Finder");
        folder.SetBounds(26, 137, 424, 26);
        Controls.Add(folder);

        Button browse = new Button();
        browse.Text = "Examinar…";
        browse.SetBounds(458, 136, 88, 28);
        browse.Click += Browse;
        Controls.Add(browse);

        desktopIcon = new CheckBox();
        desktopIcon.Text = "Crear acceso directo en el escritorio";
        desktopIcon.Checked = true;
        desktopIcon.SetBounds(26, 174, 290, 25);
        Controls.Add(desktopIcon);

        progress = new ProgressBar();
        progress.SetBounds(26, 207, 520, 18);
        progress.Visible = false;
        Controls.Add(progress);

        status = new Label();
        status.Text = "La app y FFmpeg se instalarán solo para tu usuario.";
        status.SetBounds(26, 231, 340, 22);
        Controls.Add(status);

        install = new Button();
        install.Text = "Instalar";
        install.Font = new Font("Segoe UI", 9F, FontStyle.Bold);
        install.SetBounds(450, 226, 96, 30);
        install.Click += Install;
        Controls.Add(install);
        AcceptButton = install;
        Shown += delegate(object sender, EventArgs e)
        {
            if (Environment.GetEnvironmentVariable("DJDF_TEST_MODE") == "1") Install(this, EventArgs.Empty);
        };
    }

    private void Browse(object sender, EventArgs e)
    {
        using (FolderBrowserDialog dialog = new FolderBrowserDialog())
        {
            dialog.Description = "Selecciona la carpeta donde instalar DJ Duplicate Finder";
            dialog.SelectedPath = Directory.Exists(folder.Text) ? folder.Text : Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            if (dialog.ShowDialog(this) == DialogResult.OK)
                folder.Text = Path.Combine(dialog.SelectedPath, "DJ Duplicate Finder");
        }
    }

    private void Install(object sender, EventArgs e)
    {
        if (busy) return;
        string installRoot = Path.GetFullPath(folder.Text.Trim());
        if (String.IsNullOrWhiteSpace(folder.Text))
        {
            MessageBox.Show(this, "Elige una carpeta de instalación.", Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        if (Directory.Exists(installRoot) && Directory.GetFileSystemEntries(installRoot).Length > 0)
        {
            DialogResult answer = MessageBox.Show(this, "La carpeta ya contiene archivos. La instalación actualizará los archivos de la aplicación que coincidan. ¿Continuar?", Text, MessageBoxButtons.YesNo, MessageBoxIcon.Question);
            if (answer != DialogResult.Yes) return;
        }
        busy = true;
        install.Enabled = false;
        progress.Visible = true;
        progress.Style = ProgressBarStyle.Marquee;
        status.Text = "Instalando…";
        try
        {
            Directory.CreateDirectory(installRoot);
            ExtractPayload(installRoot);
            CreateShortcuts(installRoot);
            if (Environment.GetEnvironmentVariable("DJDF_TEST_MODE") != "1") RegisterUninstall(installRoot);
            status.Text = "Instalación completa.";
            if (Environment.GetEnvironmentVariable("DJDF_TEST_MODE") == "1")
                Environment.ExitCode = 0;
            else
            {
                DialogResult launch = MessageBox.Show(this, "DJ Duplicate Finder está instalado. ¿Quieres abrirlo ahora?", Text, MessageBoxButtons.YesNo, MessageBoxIcon.Information);
                if (launch == DialogResult.Yes)
                    Process.Start(Path.Combine(installRoot, "DJ Duplicate Finder.exe"));
            }
            Close();
        }
        catch (Exception ex)
        {
            busy = false;
            install.Enabled = true;
            progress.Visible = false;
            status.Text = "La instalación no se completó.";
            if (Environment.GetEnvironmentVariable("DJDF_TEST_MODE") == "1")
            {
                File.WriteAllText(Path.Combine(Path.GetTempPath(), "DJDuplicateFinderSetup-error.txt"), ex.ToString());
                Environment.ExitCode = 1;
                Close();
            }
            else
                MessageBox.Show(this, "No se pudo completar la instalación:\r\n" + ex.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void ExtractPayload(string installRoot)
    {
        using (Stream payload = Assembly.GetExecutingAssembly().GetManifestResourceStream("Payload.zip"))
        {
            if (payload == null) throw new InvalidOperationException("No se encontró el contenido de instalación.");
            using (ZipArchive archive = new ZipArchive(payload, ZipArchiveMode.Read))
            {
                string root = Path.GetFullPath(installRoot).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
                foreach (ZipArchiveEntry entry in archive.Entries)
                {
                    string name = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
                    const string prefix = "DJ Duplicate Finder";
                    if (!name.StartsWith(prefix + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) && !String.Equals(name, prefix, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("El paquete contiene una ruta inesperada.");
                    string relative = name.Length == prefix.Length ? "" : name.Substring(prefix.Length + 1);
                    if (relative.Length == 0) continue;
                    string destination = Path.GetFullPath(Path.Combine(root, relative));
                    if (!destination.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("El paquete contiene una ruta fuera de la carpeta de instalación.");
                    if (entry.Name.Length == 0)
                    {
                        Directory.CreateDirectory(destination);
                    }
                    else
                    {
                        string parent = Path.GetDirectoryName(destination);
                        if (!Directory.Exists(parent)) Directory.CreateDirectory(parent);
                        using (Stream input = entry.Open())
                        using (FileStream output = new FileStream(destination, FileMode.Create, FileAccess.Write, FileShare.None))
                            input.CopyTo(output);
                    }
                    Application.DoEvents();
                }
            }
        }
        if (!File.Exists(Path.Combine(installRoot, "DJ Duplicate Finder.exe")))
            throw new InvalidDataException("No se encontró el ejecutable de la aplicación.");
    }

    private void CreateShortcuts(string installRoot)
    {
        string testStartMenu = Environment.GetEnvironmentVariable("DJDF_TEST_START_MENU");
        string roaming = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        if (String.IsNullOrWhiteSpace(roaming)) roaming = Environment.GetEnvironmentVariable("APPDATA");
        string startMenu = !String.IsNullOrEmpty(testStartMenu) ? testStartMenu : Path.Combine(roaming, "Microsoft", "Windows", "Start Menu", "Programs", "DJ Duplicate Finder");
        Directory.CreateDirectory(startMenu);
        string exe = Path.Combine(installRoot, "DJ Duplicate Finder.exe");
        string icon = Path.Combine(installRoot, "_internal", "assets", "DJ_Duplicate_Finder.ico");
        CreateShortcut(Path.Combine(startMenu, "DJ Duplicate Finder.lnk"), exe, installRoot, icon);
        string desktop = Environment.GetEnvironmentVariable("DJDF_TEST_DESKTOP");
        if (String.IsNullOrWhiteSpace(desktop)) desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        if (desktopIcon.Checked && !String.IsNullOrWhiteSpace(desktop))
        {
            Directory.CreateDirectory(desktop);
            CreateShortcut(Path.Combine(desktop, "DJ Duplicate Finder.lnk"), exe, installRoot, icon);
        }
    }

    private static void CreateShortcut(string path, string target, string workingDirectory, string icon)
    {
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        if (shellType == null) throw new InvalidOperationException("Windows no pudo crear el acceso directo.");
        object shell = Activator.CreateInstance(shellType);
        object shortcut = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { path });
        Type linkType = shortcut.GetType();
        linkType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, shortcut, new object[] { target });
        linkType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, shortcut, new object[] { workingDirectory });
        linkType.InvokeMember("IconLocation", BindingFlags.SetProperty, null, shortcut, new object[] { icon + ",0" });
        linkType.InvokeMember("Save", BindingFlags.InvokeMethod, null, shortcut, null);
        if (shortcut != null && System.Runtime.InteropServices.Marshal.IsComObject(shortcut))
            System.Runtime.InteropServices.Marshal.ReleaseComObject(shortcut);
        if (shell != null && System.Runtime.InteropServices.Marshal.IsComObject(shell))
            System.Runtime.InteropServices.Marshal.ReleaseComObject(shell);
    }

    private void RegisterUninstall(string installRoot)
    {
        string keyPath = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\DJDuplicateFinder";
        string powershell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe");
        string uninstallScript = Path.Combine(installRoot, "uninstall.ps1");
        long bytes = 0;
        foreach (string file in Directory.GetFiles(installRoot, "*", SearchOption.AllDirectories))
            bytes += new FileInfo(file).Length;
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(keyPath))
        {
            key.SetValue("DisplayName", "DJ Duplicate Finder");
            key.SetValue("DisplayVersion", "3.0.4");
            key.SetValue("Publisher", "DJ Duplicate Finder");
            key.SetValue("InstallLocation", installRoot);
            key.SetValue("UninstallString", "\"" + powershell + "\" -NoProfile -ExecutionPolicy Bypass -File \"" + uninstallScript + "\"");
            key.SetValue("NoModify", 1, RegistryValueKind.DWord);
            key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
            key.SetValue("EstimatedSize", (int)Math.Ceiling(bytes / 1024.0), RegistryValueKind.DWord);
        }
    }
}
