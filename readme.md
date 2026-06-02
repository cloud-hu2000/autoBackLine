



分析文件命令

# 完整流程（登录 → 抓取 → 整合）
python main.py --mode full

# 仅整合分析（不需要浏览器，直接分析已有的CSV）
python -m core.backlinks_merger --date 2026-03-22

# 通过 main.py 调用整合（指定日期）
python main.py --mode merge --date 2026-03-22

详细的每日自动化工作流说明见 `WORKFLOW.md`。

## Daily workflow

Run the whole workflow for today:

```bat
run_daily_workflow.bat
```

Run for a specific date:

```bat
run_daily_workflow.bat -Date 2026-05-26
```

Useful debug modes:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\daily_workflow.ps1 -Date 2026-05-26 -SkipScrape
powershell -NoProfile -ExecutionPolicy Bypass -File .\daily_workflow.ps1 -Date 2026-05-26 -SkipPlugin
powershell -NoProfile -ExecutionPolicy Bypass -File .\daily_workflow.ps1 -Date 2026-05-26 -NoStartPluginTask
```

The workflow writes logs to `logs\daily_workflow_YYYY-MM-DD.log`.

The Chrome extension upload step opens:

```text
chrome-extension://<PLUGIN_EXTENSION_ID>/batch.html
```

On macOS or a new machine, set the local extension id in `.env`:

```env
PLUGIN_EXTENSION_ID=eckpehelplpholpddkpmihfigodplkdp
```

If the extension page uses a custom start button, pass a selector:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\daily_workflow.ps1 -Date 2026-05-26 -PluginStartSelector "button:has-text('开始')"
```

While the plugin batch task is running, the daily workflow monitors blog pages opened by the extension:

1. Read blog URLs from the merged CSV uploaded to the extension.
2. Start the extension batch task.
3. Watch Chrome tabs opened by the extension for those blog URLs.
4. Click the floating `导出外链` button on each opened blog page.
5. Save each blog page's exported CSV to `data/input`.
6. After the batch task completes, keep only blog pages whose batch run result is `√`.
7. Merge those successful pages' CSV files with the existing URL/domain blacklists.
8. De-duplicate by domain and write `data/blog_outlinks_merged_YYYY-MM-DD.csv`.
9. Completely overwrite `data/input.xlsx` from that merged CSV.

This overwrite is intentional so the next workflow round starts from the newly discovered URLs instead of repeatedly opening the old first site.

To skip this step on macOS:

```bash
./daily_workflow.sh --skip-blog-analysis
```

To debug with an exported batch result CSV only:

```bash
python3 blog_backlink_loop.py --batch-result data/output/batch_result_xxx.csv --result-filter success
```
