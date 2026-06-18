import Cocoa
import WebKit

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    let url: URL

    init(url: URL) { self.url = url }

    func applicationDidFinishLaunching(_: Notification) {
        let cfg = WKWebViewConfiguration()
        cfg.preferences.setValue(true, forKey: "developerExtrasEnabled")

        webView = WKWebView(frame: .zero, configuration: cfg)

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "GTM OS"
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden          // hide "GTM OS" text from title bar
        window.isMovableByWindowBackground = true  // drag anywhere on the window
        window.contentView = webView
        window.setFrameAutosaveName("GTMOSWindow")
        window.center()
        window.makeKeyAndOrderFront(nil)

        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)

        webView.load(URLRequest(url: url))
    }

    func applicationShouldTerminateAfterLastWindowClosed(_: NSApplication) -> Bool { true }
}

let urlString = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "http://127.0.0.1:8765"
let app = NSApplication.shared
let delegate = AppDelegate(url: URL(string: urlString)!)
app.delegate = delegate
app.run()
