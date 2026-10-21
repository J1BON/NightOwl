# NightOwl

NightOwl is a Windows brightness app that lives in the system tray.

By [J1BON](https://jibanahammed.com/) · [GitHub](https://github.com/J1BON) · jibanahammed8@gmail.com

The brightness slider dims the desktop with a click-through shade. That is the visible control, because some monitors accept a brightness command and leave the picture unchanged. Contrast changes the picture on the desktop. 50 is the normal image: lower looks flatter, higher looks stronger. Warmth lays a steady amber tint over the screen. Deeper dark adds more shade on top of the brightness level and stays on while the window is hidden.

Closing the window hides NightOwl in the tray. Quit exits. Scrolling the tray icon changes brightness. It starts with Windows and stays in the tray.

## Install

Download `NightOwl-Setup.exe` from the Releases page of this repository. The installer does not ask for an administrator password. It adds a Start menu shortcut, a desktop shortcut, and a startup entry.

- Windows 10 or Windows 11, 64-bit
- The Microsoft Edge WebView2 runtime, which current Windows already includes

## Other monitors

NightOwl is not tied to one model. The window title comes from the monitor itself. The shade, contrast, warmth, and tray scroll work on any panel.

On a monitor whose backlight follows brightness commands, the slider writes that command and also darkens the desktop. The screen can then look darker than the number alone. Set brightness to 100 to clear the shade.

The shade and the warm tint cover the main display. Contrast changes the whole desktop, including a second screen.

## Build

You need Python 3.11, Node.js, and [Inno Setup 6](https://jrsoftware.org/isinfo.php).

```bat
npm install
npm run build
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --distpath release NightOwl.spec
```

Open `NightOwl.iss` in Inno Setup and compile it. The setup program is written to `installer\NightOwl-Setup.exe`.

To run from source instead, build the window once with `npm run build`, then start `NightOwl.bat`.

## License

[MIT](LICENSE)
