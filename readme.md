



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
chrome-extension://jhbjiamgmbmidfbdhflajegdkejianfl/batch.html
```

If the extension page uses a custom start button, pass a selector:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\daily_workflow.ps1 -Date 2026-05-26 -PluginStartSelector "button:has-text('开始')"
```
