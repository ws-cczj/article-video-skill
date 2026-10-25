"""Extract page-labelled PDF text and page images without uploading the paper."""
import argparse
import json
from pathlib import Path
import pypdfium2 as pdfium


def extract(source, output, scale=1.8):
    source, output = Path(source).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    pages = output / 'source-pages'
    pages.mkdir(exist_ok=True)
    text, empty = [], []
    with pdfium.PdfDocument(str(source)) as doc:
        count = len(doc)
        for i in range(count):
            page = doc[i]
            content = page.get_textpage().get_text_range().replace('\r\n', '\n')
            if len(content.strip()) < 30:
                empty.append(i + 1)
            text.append(f'\n\n## PDF PAGE {i + 1}\n\n{content}')
            page.render(scale=scale).to_pil().save(pages / f'page-{i+1:02}.png')
    (output / 'paper-extracted.txt').write_text(''.join(text), encoding='utf-8')
    report = {'source': str(source), 'pages': count, 'possible_ocr_pages': empty,
              'note': 'Check reading order, formulas and tables against the page images.'}
    (output / 'extraction.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf')
    parser.add_argument('--output', required=True)
    parser.add_argument('--scale', type=float, default=1.8)
    args = parser.parse_args()
    if not 0.5 <= args.scale <= 4:
        parser.error('scale must be between 0.5 and 4')
    extract(args.pdf, args.output, args.scale)
