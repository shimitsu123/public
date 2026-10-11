// QbreakTranslate.swift — 本机离线翻译（macOS Translation 框架；标题不发给任何第三方）：日文 / 英文 → 简体中文。
// 用法：echo '["原文1","原文2"]' | qbreak-translate          → [{"zh": "...", "src": "ja"}, {"zh": null, "src": "en", "err": "notInstalled"}]
//       qbreak-translate --status                            → {"ja": "installed|supported|unsupported", "en": ...}
// 语言包要先在「系统设置 → 通用 → 语言与地区 → 翻译语言」里下载（日本語、English、中文（简体））。2026-10-11 用户「通知里的新闻都要翻译为中文」。
import Foundation
import NaturalLanguage
import Translation

let target = Locale.Language(identifier: "zh-Hans")

func detect(_ s: String) -> String {
  let r = NLLanguageRecognizer()
  r.languageConstraints = [.japanese, .english, .simplifiedChinese, .traditionalChinese]
  r.processString(s)
  switch r.dominantLanguage {
  case .some(.japanese): return "ja"
  case .some(.simplifiedChinese), .some(.traditionalChinese): return "zh"
  default: return "en"
  }
}

func statusName(_ s: LanguageAvailability.Status) -> String {
  switch s {
  case .installed: return "installed"
  case .supported: return "supported"
  default: return "unsupported"
  }
}

@main struct Main {
  static func main() async {
    let av = LanguageAvailability()
    if CommandLine.arguments.contains("--status") {
      var out: [String: String] = [:]
      for src in ["ja", "en"] {
        out[src] = statusName(await av.status(from: Locale.Language(identifier: src), to: target))
      }
      print(String(data: try! JSONSerialization.data(withJSONObject: out), encoding: .utf8)!)
      return
    }
    let data = FileHandle.standardInput.readDataToEndOfFile()
    guard let texts = (try? JSONSerialization.jsonObject(with: data)) as? [String] else {
      print("[]"); exit(2)
    }
    var sessions: [String: TranslationSession] = [:]
    var results: [[String: Any]] = []
    for t in texts {
      let src = detect(t)
      if src == "zh" { results.append(["zh": t, "src": src]); continue }
      do {
        if sessions[src] == nil {
          sessions[src] = TranslationSession(installedSource: Locale.Language(identifier: src), target: target)
        }
        let r = try await sessions[src]!.translate(t)
        results.append(["zh": r.targetText, "src": src])
      } catch {
        let msg = "\(error)".contains("notInstalled") ? "notInstalled" : String("\(error)".prefix(120))
        results.append(["zh": NSNull(), "src": src, "err": msg])
      }
    }
    print(String(data: try! JSONSerialization.data(withJSONObject: results), encoding: .utf8)!)
  }
}
