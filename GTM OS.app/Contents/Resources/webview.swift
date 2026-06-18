import Cocoa
import WebKit

// GTM OS — the bundle's main executable is THIS compiled Cocoa app (a real
// Mach-O), not a shell script. macOS LaunchServices refuses to launch an .app
// whose CFBundleExecutable is an interpreted script (it times out with
// errAETimeout / -1712), so the window must come up from a proper GUI binary.
// The Python dashboard server is started asynchronously via start-server.sh so
// the launch acknowledges immediately and we never block app startup.

final class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var serverPID: Int32 = 0
    let port = 8765
    var url: URL { URL(string: "http://127.0.0.1:\(port)")! }

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

        // Show a splash immediately so the launch completes (no -1712 timeout),
        // then bring up the server and load the dashboard off the main thread.
        webView.loadHTMLString(splashHTML, baseURL: nil)
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            self?.startServerAndLoad()
        }
    }

    private func startServerAndLoad() {
        let repo = repoPath()

        if let script = Bundle.main.path(forResource: "start-server", ofType: "sh") {
            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: "/bin/bash")
            proc.arguments = [script, repo, String(port)]
            let out = Pipe()
            proc.standardOutput = out
            proc.standardError = Pipe()
            try? proc.run()
            proc.waitUntilExit()
            let text = String(data: out.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            if let r = text.range(of: "PID ") {
                let rest = text[r.upperBound...].prefix { $0.isNumber }
                serverPID = Int32(rest) ?? 0
            }
        }

        // Poll the server for up to 12s (the indexer runs before it serves).
        var up = false
        for _ in 0..<60 {
            if ping() { up = true; break }
            Thread.sleep(forTimeInterval: 0.2)
        }

        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            if up {
                self.webView.load(URLRequest(url: self.url))
            } else {
                self.showFailure(repo)
            }
        }
    }

    private func ping() -> Bool {
        var req = URLRequest(url: url)
        req.timeoutInterval = 1
        let sem = DispatchSemaphore(value: 0)
        var ok = false
        let task = URLSession.shared.dataTask(with: req) { _, resp, _ in
            if let http = resp as? HTTPURLResponse, http.statusCode == 200 { ok = true }
            sem.signal()
        }
        task.resume()
        _ = sem.wait(timeout: .now() + 1.5)
        return ok
    }

    // The bundle lives at <repo>/GTM OS.app, so the repo is its parent directory.
    private func repoPath() -> String {
        (Bundle.main.bundlePath as NSString).deletingLastPathComponent
    }

    private func showFailure(_ repo: String) {
        let alert = NSAlert()
        alert.messageText = "GTM OS failed to start"
        alert.informativeText = "The dashboard server did not respond. Check \(repo)/dashboard/server.log for details."
        alert.runModal()
        NSApp.terminate(nil)
    }

    func applicationWillTerminate(_: Notification) {
        if serverPID > 0 { kill(serverPID, SIGTERM) }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_: NSApplication) -> Bool { true }

    private var splashHTML: String {
        """
        <html><body style="margin:0;background:#16181c;color:#9aa4af;\
        font:14px -apple-system,system-ui;display:flex;align-items:center;\
        justify-content:center;height:100vh">Starting GTM OS…</body></html>
        """
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
