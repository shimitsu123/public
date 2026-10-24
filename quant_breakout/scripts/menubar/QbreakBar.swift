// QbreakBar — Mac 菜单栏上的 qbreak 状态（〔App 化〕B；scripts/install_launchd_menubar.sh 编译、注册成 LaunchAgent com.qbreak.menubar）。
// 每 2 分钟叫一次 `python -m qbreak.mac_status --write`（只读：执行器的文件、launchctl list、tailscale status），读数据目录的
// out/mac_status.json 显示 ✓ / ! / ✕。不下单、不读密钥、不连券商；菜单里只有「打开」「复制」「刷新」。
import AppKit

final class QbreakBar: NSObject, NSApplicationDelegate {
    private var item: NSStatusItem!
    private var timer: Timer?
    private let env = ProcessInfo.processInfo.environment
    private lazy var home = env["QBREAK_LIVEU_HOME"] ?? (NSHomeDirectory() + "/.qbreak/home")
    private lazy var python = env["QBREAK_PYTHON"] ?? (NSHomeDirectory() + "/.qbreak/venv/bin/python")
    private lazy var proj = env["QBREAK_PROJ"] ?? (NSHomeDirectory() + "/qbreak-src/quant_breakout")
    private var status: [String: Any] = [:]

    func applicationDidFinishLaunching(_ notification: Notification) {
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        setTitle("qbreak …", color: .secondaryLabelColor)
        render()
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 120, repeats: true) { [weak self] _ in self?.refresh() }
    }

    private func setTitle(_ text: String, color: NSColor) {
        item.button?.attributedTitle = NSAttributedString(string: text, attributes: [
            .foregroundColor: color, .font: NSFont.menuBarFont(ofSize: 0)])
    }

    @objc func refresh() {
        DispatchQueue.global(qos: .utility).async {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: self.python)
            p.arguments = ["-m", "qbreak.mac_status", "--write"]
            p.currentDirectoryURL = URL(fileURLWithPath: self.proj)
            var e = self.env
            e["QBREAK_HOME"] = self.home
            p.environment = e
            p.standardOutput = FileHandle.nullDevice
            p.standardError = FileHandle.nullDevice
            do { try p.run(); p.waitUntilExit() } catch {}
            DispatchQueue.main.async { self.render() }
        }
    }

    private func load() -> [String: Any] {
        let url = URL(fileURLWithPath: home + "/out/mac_status.json")
        guard let d = try? Data(contentsOf: url),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return [:] }
        return j
    }

    private func render() {
        status = load()
        let level = status["level"] as? String ?? ""
        let title = status["title"] as? String ?? "qbreak ?"
        let color: NSColor = level == "ok" ? .systemGreen : level == "warn" ? .systemOrange : level == "bad" ? .systemRed : .secondaryLabelColor
        setTitle(title, color: color)
        let menu = NSMenu()
        let at = status["at"] as? String ?? "—"
        menu.addItem(withTitle: "qbreak（\(at) JST 的检查）", action: nil, keyEquivalent: "")
        for it in status["items"] as? [[String: Any]] ?? [] {
            let lv = it["level"] as? String ?? ""
            let mark = lv == "ok" ? "✓" : lv == "warn" ? "!" : lv == "bad" ? "✕" : "·"
            var text = "\(mark) \(it["name"] as? String ?? "")：\(it["text"] as? String ?? "")"
            if text.count > 90 { text = String(text.prefix(88)) + "…" }
            let mi = NSMenuItem(title: text, action: nil, keyEquivalent: "")
            mi.toolTip = it["text"] as? String
            menu.addItem(mi)
        }
        menu.addItem(.separator())
        add(menu, "打开操作面板（Mac）", #selector(openPanel))
        add(menu, "打开账本页", #selector(openPage))
        add(menu, "打开市场仪表盘", #selector(openDashboard))
        if status["phone_url"] as? String != nil { add(menu, "复制手机用的地址", #selector(copyPhone)) }
        add(menu, "现在刷新", #selector(refresh))
        menu.addItem(.separator())
        add(menu, "退出菜单栏图标（下次登录自动回来）", #selector(quit))
        item.menu = menu
    }

    private func add(_ menu: NSMenu, _ title: String, _ sel: Selector) {
        let mi = NSMenuItem(title: title, action: sel, keyEquivalent: "")
        mi.target = self
        menu.addItem(mi)
    }

    private func open(_ s: String?) {
        guard let s = s, !s.isEmpty else { return }
        let url = s.hasPrefix("http") ? URL(string: s) : URL(fileURLWithPath: s)
        if let u = url { NSWorkspace.shared.open(u) }
    }

    @objc func openPanel() { open(status["panel_url"] as? String ?? "http://127.0.0.1:8765/") }
    @objc func openPage() { open(status["page"] as? String) }
    @objc func openDashboard() { open(status["dashboard"] as? String) }
    @objc func copyPhone() {
        guard let s = status["phone_url"] as? String else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(s, forType: .string)
    }
    @objc func quit() { NSApp.terminate(nil) }
}

let app = NSApplication.shared
let delegate = QbreakBar()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
