# MiniMax Mini-Agent + Free Web Search (v13.0.0)

零成本实时网络搜索，无需 API Key。

```bash
pip install free-web-search-ultimate==13.0.0
```

```python
from free_web_search_ultimate import UltimateSearcher
searcher = UltimateSearcher()
results = searcher.search('MiniMax AI 最新模型', max_results=3)
for r in results:
    print(r['title'], r['url'])
```

**PyPI:** https://pypi.org/project/free-web-search-ultimate/
**GitHub:** https://github.com/wd041216-bit/free-web-search-ultimate
