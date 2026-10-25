"""Build matching Chinese Markdown/LaTeX summaries from reviewed structured text."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess


def tex(text):
    chars = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
             '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}
    return ''.join(chars.get(c, c) for c in str(text)).replace('[1]', r'\cite{source}')


def build(source, compile_pdf=False):
    source = Path(source).resolve()
    root = source.parent
    data = json.loads(source.read_text(encoding='utf-8-sig'))
    for key in ('title', 'original_title', 'authors', 'publication', 'url', 'scope', 'abstract', 'keywords', 'sections', 'reference'):
        if not data.get(key):
            raise ValueError(f'Missing {key}')
    template = Path(__file__).resolve().parents[1] / 'assets/chinese-summary-template.tex'
    preamble = template.read_text(encoding='utf-8').split(r'\begin{document}')[0]
    md = [f'# {data["title"]}', '\n文献阅读总结']
    body = [r'\begin{document}', r'\begin{center}{\zihao{2}\bfseries ' + tex(data['title']) +
            r'\par}\vspace{6bp}{\zihao{5}文献阅读总结\par}\end{center}']
    for label, value in [('原文标题', data['original_title']), ('作者', data['authors']),
                         ('发表信息', data['publication']), ('来源', data['url']), ('阅读范围', data['scope'])]:
        md.append(f'\n**{label}：** {value}')
        content = r'\url{' + value + '}' if label == '来源' else tex(value)
        body.append(r'\noindent\textbf{' + label + '：}' + content + r'\par')
    md += ['\n## 摘要', data['abstract'], '\n**关键词：** ' + '；'.join(data['keywords'])]
    body += [r'\begin{abstract}', tex(data['abstract']), r'\end{abstract}',
             r'\noindent\textbf{关键词：}' + tex('；'.join(data['keywords'])) + r'\par']
    for idx, section in enumerate(data['sections'], 1):
        md.append(f'\n## {idx} {section["title"]}')
        body.append(r'\section{' + tex(section['title']) + '}')
        for item in section['blocks']:
            if isinstance(item, str):
                md.append('\n' + item)
                body.append(tex(item) + '\n')
            elif item['type'] == 'equation':
                md += ['\n$$\n' + item['latex'] + '\n$$', item['explanation']]
                body += [r'\begin{equation}' + item['latex'] + r'\end{equation}', tex(item['explanation']) + '\n']
            elif item['type'] == 'table':
                headers, rows = item['headers'], item['rows']
                if any(len(row) != len(headers) for row in rows):
                    raise ValueError('Table row width differs from header')
                md += ['\n' + item['caption'], '| ' + ' | '.join(headers) + ' |',
                       '| ' + ' | '.join(['---']*len(headers)) + ' |']
                md += ['| ' + ' | '.join(map(str, row)) + ' |' for row in rows]
                body += [r'\begin{table}[htbp]\centering\small', r'\caption{' + tex(item['caption']) + '}',
                         r'\begin{tabularx}{\linewidth}{' + 'X'*len(headers) + r'}\toprule',
                         ' & '.join(map(tex, headers)) + r'\\\midrule']
                body += [' & '.join(map(tex, row)) + r'\\' for row in rows]
                body += [r'\bottomrule\end{tabularx}\end{table}']
            else:
                raise ValueError(f'Unknown block type: {item["type"]}')
    md += ['\n## 参考文献', '[1] ' + data['reference']]
    body += [r'\begin{thebibliography}{9}\bibitem{source}', tex(data['reference']), r'\end{thebibliography}', r'\end{document}']
    (root / 'summary.md').write_text('\n\n'.join(md) + '\n', encoding='utf-8')
    (root / 'summary.tex').write_text(preamble + '\n'.join(body) + '\n', encoding='utf-8')
    if compile_pdf:
        engine = shutil.which('xelatex')
        if not engine:
            raise RuntimeError('XeLaTeX missing; summary.md and summary.tex were generated.')
        for run in range(2):
            cmd = [engine, '-interaction=nonstopmode', '-halt-on-error', '-no-shell-escape', 'summary.tex']
            result = subprocess.run(cmd, cwd=root, capture_output=True, timeout=180)
            (root / f'compile-{run+1}.txt').write_bytes(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError(f'XeLaTeX failed. See {root / f"compile-{run+1}.txt"}')
        log = (root / 'summary.log').read_text(encoding='utf-8', errors='replace')
        problems = re.findall(r'^.*(?:Missing character|Overfull|undefined references|Citation .* undefined).*$', log, re.M)
        if problems:
            raise RuntimeError('PDF requires repair:\n' + '\n'.join(problems))
        import pypdfium2 as pdfium
        previews = root / 'summary-pages'
        previews.mkdir(exist_ok=True)
        with pdfium.PdfDocument(str(root / 'summary.pdf')) as doc:
            for i in range(len(doc)):
                doc[i].render(scale=1.5).to_pil().save(previews / f'page-{i+1:02}.png')
            print(f'Compiled {len(doc)} pages. Inspect summary-pages before accepting layout.')
    print(f'Generated summary.md and summary.tex in {root}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary_json')
    parser.add_argument('--compile', action='store_true')
    args = parser.parse_args()
    build(args.summary_json, args.compile)
