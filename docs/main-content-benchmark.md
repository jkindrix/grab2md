# Main-content extraction benchmark

This benchmark answers whether `html2md` should replace raw `markdownify`
conversion with a general main-content extractor. It uses deterministic article,
documentation, and product fixtures in
[`benchmarks/main_content/fixtures.json`](../benchmarks/main_content/fixtures.json).
Each fixture identifies content that must survive and boilerplate that should be
removed. Structural fidelity is reviewed alongside those marker scores.

## Reproduction

The recorded run used Python 3.11, Markdownify 1.2.3, Trafilatura 2.1.0, and
readability-lxml 0.8.4.1. Candidate packages are intentionally not project
dependencies. Install them in a disposable environment and run:

```bash
python -m pip install markdownify==1.2.3 trafilatura==2.1.0 \
  readability-lxml==0.8.4.1 lxml_html_clean
python benchmarks/main_content/benchmark.py
```

## Results

| Fixture | Engine | Required recall | Boilerplate rejection |
|---|---|---:|---:|
| Article | Raw | 100% | 0% |
| Article | Readability | 57% | 100% |
| Article | Trafilatura | 100% | 100% |
| Documentation | Raw | 100% | 0% |
| Documentation | Readability | 100% | 22% |
| Documentation | Trafilatura | 100% | 78% |
| Product | Raw | 100% | 0% |
| Product | Readability | 50% | 100% |
| Product | Trafilatura | 100% | 45% |

Trafilatura clearly improves the article fixture. It does not provide a safe
universal replacement: its Markdown result flattens documentation headings and
the fenced code block, and it retains more than half of the product fixture's
boilerplate. Readability drops the article table and half of the product's
required content.

## Decision

Do not add either extractor or change the conversion default. The measured
trade-off is content-type dependent, so a universal switch would exchange known
boilerplate for silent loss of required content or structure. Raw conversion
remains explicitly available with `--no-trim`; `--trim` remains the opt-in/domain
rule mechanism for known sites.

Reconsider an extractor only with a stated target content class and a larger,
versioned corpus. An implementation proposal must meet all three gates:

1. no lower required-content recall than raw conversion;
2. materially better boilerplate rejection for the target class; and
3. no regression in headings, links, images, tables, lists, or fenced code.

This decision follows the extractors' own documented trade-off: main-content
heuristics balance precision and recall and may preserve different elements
depending on output constraints. It is evidence against a universal default,
not evidence that extraction is never useful.
