param([string]$Executable,[string]$IconFile)
$ErrorActionPreference = 'SilentlyContinue'
if (-not (Test-Path -LiteralPath $Executable) -or -not (Test-Path -LiteralPath $IconFile)) { exit 0 }
$roaming = $env:APPDATA
if (-not $roaming) { $roaming = [Environment]::GetFolderPath([Environment+SpecialFolder]::ApplicationData) }
$desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
$folders = @(
  (Join-Path $roaming 'Microsoft\Windows\Start Menu\Programs\DJ Duplicate Finder'),
  $desktop,
  (Join-Path $roaming 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar')
)
$expected = [IO.Path]::GetFullPath($Executable)
$shell = New-Object -ComObject WScript.Shell
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class DJDFShellNotify { [DllImport("shell32.dll")] public static extern void SHChangeNotify(int eventId, uint flags, IntPtr item1, IntPtr item2); }'
foreach ($folder in $folders) {
  if (-not (Test-Path -LiteralPath $folder)) { continue }
  foreach ($link in (Get-ChildItem -LiteralPath $folder -Filter '*.lnk' -File)) {
    try {
      $shortcut = $shell.CreateShortcut($link.FullName)
      if ([IO.Path]::GetFullPath($shortcut.TargetPath).Equals($expected, [StringComparison]::OrdinalIgnoreCase)) {
        $shortcut.IconLocation = "$IconFile,0"
        $shortcut.Save()
        $nativePath = [Runtime.InteropServices.Marshal]::StringToHGlobalUni($link.FullName)
        [DJDFShellNotify]::SHChangeNotify(0x00002000, 0x0005, $nativePath, [IntPtr]::Zero)
        [Runtime.InteropServices.Marshal]::FreeHGlobal($nativePath)
      }
    } catch { }
  }
}
