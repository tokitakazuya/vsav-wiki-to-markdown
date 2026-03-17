# vsav-wiki-to-markdown
VampireSavior攻略wiki( https://seesaawiki.jp/vswiki/ )のhtmlをmarkdown形式に変換します

## 概要

Seesaa Wikiで構築されたVampireSavior攻略wikiのHTMLファイルをMarkdown形式に自動変換するPythonスクリプトです。

このスクリプトはGitHub Copilot(Claude Haiku 4.5)を使用して作成しました。

## 要件

- Python 3.6以上

- ## 使い方

### 1. target フォルダ内のすべてのHTMLファイルを変換

```bash
python convert.py
```

`./target/` フォルダ内のすべての `.htm` および `.html` ファイルがMarkdownに変換され、同じフォルダに `.md` ファイルとして保存されます。

### 2. 特定のHTMLファイルのみを変換

```bash
python convert.py target/Q&A.htm
```

指定したファイルのみ変換され、同じディレクトリに `.md` ファイルが生成されます。

## 出力形式

HTMLから以下のMarkdown要素に自動変換されます：

| HTML | Markdown |
|------|----------|
| `<h2>` | `# ` (h1に昇格) |
| `<h3>` | `## ` |
| `<a href="...">` | `[text](url)` |
| `<strong>`, `<b>` | `**text**` |
| `<em>`, `<i>` | `*text*` |
| `<ul>` | `- ` リスト |
| `<ol>` | `1. ` 番号付きリスト |
| `<table>` | Markdownテーブル |
| `<blockquote>` | `> ` ブロッククォート |

### フィルタリング

以下の要素は自動削除されます：

- `<script>`, `<style>`, `<iframe>`, `<noscript>` タグ
- 編集ボタン (`a[title="部分編集"]`)
- ページメタデータ (ID: `page-social-link-top`, `page-footer` など)
- カテゴリ情報やナビゲーション要素

## ライセンス

WTFPL
