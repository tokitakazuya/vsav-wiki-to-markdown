#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import html
import sys
from html.parser import HTMLParser
from pathlib import Path


class CharsetExtractor(HTMLParser):
    """HTMLのcharset属性を抽出"""
    def __init__(self):
        super().__init__()
        self.charset = None

    def handle_starttag(self, tag, attrs):
        if tag == 'meta':
            attrs_dict = dict(attrs)
            if 'charset' in attrs_dict:
                self.charset = attrs_dict['charset']
            elif attrs_dict.get('http-equiv', '').lower() == 'content-type':
                content = attrs_dict.get('content', '')
                match = re.search(r'charset\s*=\s*([^\s;]+)', content, re.IGNORECASE)
                if match:
                    self.charset = match.group(1)
            if self.charset:
                raise StopIteration


def detect_encoding(file_path):
    """ファイルのエンコーディングを検出"""
    try:
        with open(file_path, 'rb') as f:
            sample = f.read(2048)

        for encoding in ['utf-8', 'EUC-JP', 'shift_jis', 'cp932', 'latin-1']:
            try:
                text = sample.decode(encoding, errors='ignore')
                extractor = CharsetExtractor()
                try:
                    extractor.feed(text)
                except StopIteration:
                    pass
                if extractor.charset:
                    return extractor.charset.upper()
            except:
                continue
    except:
        pass

    return None


def extract_content(html_content):
    """必要なコンテンツのみを抽出: #page-header-innerのh2と更新日時、#page-body-innerの最初のdiv.user-area"""
    class ContentExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.content = []
            self.in_page_header = False
            self.in_page_body = False
            self.in_user_area = False
            self.in_h2 = False
            self.in_update_p = False
            self.user_area_found = False  # 最初のuser-areaを見つけたフラグ
            self.skip_history = False
            self.user_area_depth = 0  # user-area内のdiv深さ

        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)

            # page-header-inner開始
            if tag == 'div' and attrs_dict.get('id') == 'page-header-inner':
                self.in_page_header = True
                return

            # page-body-inner開始
            if tag == 'div' and attrs_dict.get('id') == 'page-body-inner':
                self.in_page_body = True
                return

            # page-headerではh2とp.updateだけを抽出
            if self.in_page_header:
                if tag == 'h2':
                    self.in_h2 = True
                    self.content.append('<h1>')  # h2をh1に昇格
                elif tag == 'p' and 'update' in attrs_dict.get('class', ''):
                    self.in_update_p = True
                    self.content.append('<p>')
                elif tag == 'span' and attrs_dict.get('class') == 'history' and self.in_update_p:
                    self.skip_history = True
                    return
                elif tag == 'a' and self.skip_history:
                    return
                    return
                else:
                    # その他の要素はスキップ
                    return

            # page-bodyで最初のuser-areaを見つける
            elif self.in_page_body and not self.user_area_found:
                if tag == 'div' and 'user-area' in attrs_dict.get('class', ''):
                    self.in_user_area = True
                    self.user_area_found = True
                    self.user_area_depth = 0
                    return

            # user-area内のコンテンツ
            elif self.in_user_area:
                if tag == 'div':
                    self.user_area_depth += 1
                self.content.append(self.get_starttag_text())

        def handle_endtag(self, tag):
            # page-header内：h2またはp終了
            if self.in_page_header:
                if tag == 'h2' and self.in_h2:
                    self.in_h2 = False
                    self.content.append('</h1>\n')
                    return
                elif tag == 'p' and self.in_update_p:
                    self.in_update_p = False
                    self.content.append('</p>\n')
                    return
                elif tag == 'div':
                    self.in_page_header = False
                    return

            # span.historyをスキップ
            if self.skip_history and tag == 'span':
                self.skip_history = False
                return

            # user-area内
            if self.in_user_area:
                if tag == 'div':
                    if self.user_area_depth > 0:
                        self.user_area_depth -= 1
                        self.content.append(f'</{tag}>')
                    else:
                        # user-areaの終了
                        self.in_user_area = False
                        self.in_page_body = False
                else:
                    self.content.append(f'</{tag}>')

        def handle_data(self, data):
            # skip_history中はデータをスキップ
            if self.skip_history:
                return

            # h2またはp.update内のデータのみ抽出
            if self.in_h2 or self.in_update_p:
                self.content.append(data)
            elif self.in_user_area:
                self.content.append(data)

        def handle_startendtag(self, tag, attrs):
            if self.in_user_area:
                self.content.append(self.get_starttag_text())

    extractor = ContentExtractor()
    try:
        extractor.feed(html_content)
    except Exception as e:
        print(f'警告: HTMLパース中にエラーが発生しました: {e}')

    if extractor.content:
        return ''.join(extractor.content)
    return None


class HTMLToMarkdownConverter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.markdown = []
        self.current_list = None
        self.list_level = 0
        self.in_blockquote = False
        self.in_table = False
        self.table_rows = []
        self.current_row = []
        self.skip_content = False
        self.skip_element = False  # 特定要素（例：a[title="部分編集"]）をスキップするフラグ
        self.skip_tags = {'script', 'style', 'iframe', 'noscript'}
        self.skip_ids = {'information-box', 'page-social-link-top', 'page-social-link-bottom',
                         'page-attachedfile', 'page-extra', 'page-posted', 'page-category',
                         'page-toplink', 'page-footer', 'adsense-box', 'ads-box'}

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if attrs_dict.get('id') in self.skip_ids:
            self.skip_content = True
            return

        if tag in self.skip_tags:
            self.skip_content = True
            return

        if self.skip_content or self.skip_element:
            return

        # a タグで title="部分編集" の場合はスキップ
        if tag == 'a' and attrs_dict.get('title') == '部分編集':
            self.skip_element = True
            return

        if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            level = int(tag[1]) - 1
            self.markdown.append('\n' + '#' * level + ' ' if level > 0 else '\n# ')

        elif tag == 'p':
            self.markdown.append('\n')

        elif tag == 'br':
            self.markdown.append('\n')

        elif tag == 'a':
            href = attrs_dict.get('href', '')
            self.markdown.append(f'[')
            self.link_href = href

        elif tag in ['strong', 'b']:
            self.markdown.append('**')

        elif tag in ['em', 'i']:
            self.markdown.append('*')

        elif tag in ['del', 'strike']:
            self.markdown.append('~~')

        elif tag == 'ul':
            self.current_list = 'ul'
            self.list_level += 1

        elif tag == 'ol':
            self.current_list = 'ol'
            self.list_level += 1
            self.list_counter = 0

        elif tag == 'li':
            if self.current_list == 'ul':
                self.markdown.append('\n' + '  ' * (self.list_level - 1) + '- ')
            elif self.current_list == 'ol':
                self.list_counter += 1
                self.markdown.append('\n' + '  ' * (self.list_level - 1) + f'{self.list_counter}. ')

        elif tag == 'blockquote':
            self.in_blockquote = True
            self.markdown.append('\n')

        elif tag == 'table':
            self.in_table = True
            self.table_rows = []

        elif tag == 'tr':
            self.current_row = []

        elif tag in ['td', 'th']:
            self.markdown.append('|')

        elif tag == 'img':
            alt = attrs_dict.get('alt', '')
            src = attrs_dict.get('src', '')
            if src:
                self.markdown.append(f'![{alt}]({src})')

        elif tag == 'hr':
            self.markdown.append('\n---\n')

    def handle_endtag(self, tag):
        if self.skip_content:
            return

        # スキップ中の </a> タグでスキップ終了
        if tag == 'a' and self.skip_element:
            self.skip_element = False
            return

        if self.skip_element:
            return

        if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            self.markdown.append('\n\n')

        elif tag == 'p':
            self.markdown.append('\n\n')

        elif tag == 'a':
            self.markdown.append(f']({self.link_href})')

        elif tag in ['strong', 'b']:
            self.markdown.append('**')

        elif tag in ['em', 'i']:
            self.markdown.append('*')

        elif tag in ['del', 'strike']:
            self.markdown.append('~~')

        elif tag == 'ul':
            self.list_level -= 1
            if self.list_level == 0:
                self.current_list = None
            self.markdown.append('\n')

        elif tag == 'ol':
            self.list_level -= 1
            if self.list_level == 0:
                self.current_list = None
            self.markdown.append('\n')

        elif tag == 'blockquote':
            self.in_blockquote = False
            self.markdown.append('\n\n')

        elif tag == 'table':
            self.in_table = False
            if self.table_rows:
                md_table = self.convert_table_to_markdown(self.table_rows)
                self.markdown.append(md_table)
            self.markdown.append('\n\n')

        elif tag == 'tr':
            if self.in_table:
                self.table_rows.append(self.current_row)

    def handle_data(self, data):
        if self.skip_content or self.skip_element:
            return

        text = data.strip()

        if text:
            if self.in_blockquote:
                for line in text.split('\n'):
                    if line.strip():
                        self.markdown.append('> ' + line.strip() + '\n')
            elif self.in_table:
                self.current_row.append(text)
            else:
                self.markdown.append(text)

    def convert_table_to_markdown(self, rows):
        if not rows:
            return ''

        md = ''
        for i, row in enumerate(rows):
            md += '| ' + ' | '.join(row) + ' |\n'
            if i == 0:
                md += '| ' + ' | '.join(['---'] * len(row)) + ' |\n'

        return md

    def get_markdown(self):
        result = ''.join(self.markdown)
        result = re.sub(r'\n\n\n+', '\n\n', result)
        return result.strip()


def convert_file(html_file):
    """単一ファイルを変換する"""
    html_filename = html_file.name

    if not html_file.exists():
        print(f'エラー: {html_file} が見つかりません')
        return False

    detected_charset = detect_encoding(html_file)
    print(f'{html_filename}: {detected_charset or "不明"}')

    if detected_charset:
        encodings = [detected_charset, 'utf-8', 'EUC-JP', 'shift_jis', 'cp932', 'latin-1', 'iso-8859-1']
    else:
        encodings = ['utf-8', 'utf-8-sig', 'EUC-JP', 'shift_jis', 'cp932', 'latin-1', 'iso-8859-1']

    html_content = None
    for encoding in encodings:
        try:
            with open(html_file, 'r', encoding=encoding, errors='ignore') as f:
                html_content = f.read()
            if html_content:
                print(f'  → {encoding} で読み込みました')
                break
        except (UnicodeDecodeError, LookupError):
            continue

    if html_content is None:
        print(f'エラー: {html_filename} をデコードできません')
        return False

    container_html = extract_content(html_content)

    if not container_html:
        print(f'警告: {html_filename} で必要なコンテンツが見つかりません')
        # 見つからなくても処理を続ける

    converter = HTMLToMarkdownConverter()
    if container_html:
        converter.feed(container_html)
    markdown = converter.get_markdown()

    # 「このページを編集する」以降の不要な部分を削除
    markdown = re.sub(
        r'\[このページを編集する\].*?(?=\n\n[#]|\Z)',
        '',
        markdown,
        flags=re.DOTALL | re.IGNORECASE
    )

    # ページメタデータ（カテゴリ、トップリンクなど）を削除
    markdown = re.sub(
        r'\n+カテゴリ.*?(?=\n\n[#]|\Z)',
        '',
        markdown,
        flags=re.DOTALL | re.IGNORECASE
    )
    markdown = re.sub(
        r'\n+\[.*?先頭へ\].*?(?=\Z)',
        '',
        markdown,
        flags=re.DOTALL
    )

    # 連続した改行をクリーンアップ
    markdown = re.sub(r'\n\n\n+', '\n\n', markdown).strip()

    output_filename = html_file.stem + '.md'
    output_file = html_file.parent / output_filename
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(markdown)

    print(f'変換完了: {output_file}')
    print('----')
    print(markdown[:300] + '...' if len(markdown) > 300 else markdown)
    return True


def main():
    # コマンドライン引数の処理
    if len(sys.argv) > 1:
        # 特定のファイルが指定された場合
        html_filename = sys.argv[1]
        html_file = Path(__file__).parent / html_filename
        convert_file(html_file)
    else:
        # 引数がない場合は target フォルダのすべてのHTMLファイルを処理
        target_folder = Path(__file__).parent / 'target'

        if not target_folder.exists():
            print(f'エラー: {target_folder} が見つかりません')
            return

        # .htm と .html ファイルをすべて取得
        html_files = sorted(list(target_folder.glob('*.htm')) + list(target_folder.glob('*.html')))

        if not html_files:
            print(f'警告: {target_folder} 内にHTMLファイルが見つかりません')
            return

        print(f'{len(html_files)} 個のファイルを処理します\n')

        success_count = 0
        fail_count = 0

        for html_file in html_files:
            try:
                if convert_file(html_file):
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                print(f'エラー: {html_file.name} の処理中にエラーが発生しました: {e}')
                fail_count += 1
            print()

        print(f'\n処理完了: {success_count} 個成功, {fail_count} 個失敗')


if __name__ == '__main__':
    main()
