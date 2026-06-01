# 每日外链自动化工作流说明

本文档说明每日外链导出、合并、上传到 Chrome 插件批量处理页的完整流程、实现方式和使用教程。

## 1. 工作流目标

每天更新 `data\input.xlsx` 后，用一个入口脚本完成以下事情：

1. 启动带远程调试端口的 Chrome。
2. 运行现有网站自动化程序，登录网站并导出外链 CSV。
3. 等待下载目录中的 CSV 文件稳定。
4. 合并当天外链列表，生成当天的整合 CSV。
5. 打开已安装的 Chrome 插件设置页面，并点击“打开批量处理”进入批量处理页。
6. 上传整合后的 CSV。
7. 自动点击开始执行任务。
8. 等待插件批量任务运行完成。
9. 点击【导出结果 CSV】。
10. 将导出的结果 CSV 保存到 `data\output`。
11. 写入日志，方便失败后排查。

## 2. 相关文件

| 文件 | 作用 |
| --- | --- |
| `run_daily_workflow.bat` | 日常入口，双击运行整个工作流。 |
| `daily_workflow.ps1` | 总控脚本，串联 Chrome、抓取、合并、插件上传。 |
| `start_chrome_debug.bat` | 启动 Chrome debug 模式，端口默认 `9222`。 |
| `main.py` | 现有网站登录、节点选择、外链导出主流程。 |
| `merge_only.py` | 合并当天 `data\downloads` 下的导出 CSV。 |
| `extension_batch_upload.py` | 打开 Chrome 插件设置页，点击进入批量页，上传 CSV 并点击开始。 |
| `data\input.xlsx` | 每日输入文件。 |
| `data\downloads\` | 网站导出的原始 CSV 所在目录。 |
| `data\backlinks_merged_YYYY-MM-DD.csv` | 合并后的当天 CSV。 |
| `logs\daily_workflow_YYYY-MM-DD.log` | 每日工作流日志。 |
| `logs\screenshots\` | 插件页面或网站自动化失败时的截图目录。 |

## 3. 完整流程

```text
更新 data\input.xlsx
  -> run_daily_workflow.bat
  -> start_chrome_debug.bat
  -> 等待 http://127.0.0.1:9222/json/version 可访问
  -> python main.py --mode full --date YYYY-MM-DD
  -> 等待 data\downloads\backlinks_export_YYYY-MM-DD*.csv 稳定
  -> python merge_only.py --date YYYY-MM-DD
  -> 生成 data\backlinks_merged_YYYY-MM-DD.csv
  -> python extension_batch_upload.py --csv 合并文件
  -> 打开 chrome-extension://jhbjiamgmbmidfbdhflajegdkejianfl/options.html
  -> 点击【打开批量处理】
  -> 进入 chrome-extension://jhbjiamgmbmidfbdhflajegdkejianfl/batch.html
  -> 上传 CSV
  -> 点击开始执行
  -> 等待批量任务完成
  -> 点击【导出结果 CSV】
  -> 保存到 data\output
```

## 4. 实现方式

### 4.1 Chrome debug

`start_chrome_debug.bat` 使用独立 Chrome 用户目录：

```text
browser\data
```

并开启：

```text
--remote-debugging-port=9222
```

这样 Playwright 可以通过 Chrome DevTools Protocol 连接到真实 Chrome，而不是另起一个没有插件和登录状态的临时浏览器。

注意：这个独立 profile 需要已经登录网站，并且需要安装目标插件。如果插件只安装在你日常 Chrome 里，自动化 profile 里不会天然拥有它。首次运行前建议先运行 `start_chrome_debug.bat`，确认这个窗口里能打开：

```text
chrome-extension://jhbjiamgmbmidfbdhflajegdkejianfl/batch.html
```

当前工作流会优先打开：

```text
chrome-extension://jhbjiamgmbmidfbdhflajegdkejianfl/options.html
```

再点击页面中的“打开批量处理”按钮进入 `batch.html`，这样和人工操作路径保持一致。

### 4.2 抓取和导出

总控脚本调用：

```text
python main.py --mode full --date YYYY-MM-DD
```

这个步骤沿用现有代码，负责登录、选择节点、读取 `data\input.xlsx`、逐个域名导出外链 CSV。

该步骤默认最长等待 240 分钟，可通过 `-ScrapeTimeoutMinutes` 修改。

### 4.3 判断导出完成

导出完成后，总控脚本不会只靠固定 sleep，而是检查：

1. `data\downloads` 中是否出现 `backlinks_export_YYYY-MM-DD*.csv`。
2. 是否不存在 `.crdownload` 临时下载文件。
3. 文件名、大小、修改时间是否连续稳定 10 秒。

这样可以避免文件还没下载完就进入合并。

### 4.4 合并 CSV

总控脚本调用：

```text
python merge_only.py --date YYYY-MM-DD
```

默认输出：

```text
data\backlinks_merged_YYYY-MM-DD.csv
```

### 4.5 插件上传

插件上传由 `extension_batch_upload.py` 完成：

1. 连接 `127.0.0.1:9222`。
2. 打开插件设置页：

   ```text
   chrome-extension://jhbjiamgmbmidfbdhflajegdkejianfl/options.html
   ```

3. 点击设置页中的“打开批量处理”按钮。
4. 等待插件批量页打开：

   ```text
   chrome-extension://jhbjiamgmbmidfbdhflajegdkejianfl/batch.html
   ```

5. 查找页面中的 `input[type="file"]`。
6. 把合并后的 CSV 设置到文件输入框，并触发插件自己的文件解析逻辑。
7. 查找开始按钮并点击。
8. 等待插件状态变成 `completed`。
9. 点击 `#exportBtn` 导出结果 CSV。
10. 不修改 Chrome 下载目录；脚本会监控默认 Downloads，并把新导出的 `batch_result_*.csv` 移动到 `data\output`。

如果按钮识别失败，脚本会截图，并在日志里输出页面上的按钮文本，方便后续补充精确选择器。

## 5. 使用教程

### 5.1 每天正常运行

1. 更新：

   ```text
   data\input.xlsx
   ```

2. 双击：

   ```text
   run_daily_workflow.bat
   ```

3. 查看日志：

   ```text
   logs\daily_workflow_YYYY-MM-DD.log
   ```

### 5.2 指定日期运行

```bat
run_daily_workflow.bat -Date 2026-05-26
```

### 5.3 只合并并上传插件

如果当天原始 CSV 已经导出过，不想重新抓取：

```bat
run_daily_workflow.bat -Date 2026-05-26 -SkipScrape
```

### 5.4 只抓取和合并，不上传插件

```bat
run_daily_workflow.bat -Date 2026-05-26 -SkipPlugin
```

### 5.5 上传插件但不点击开始

用于第一次调试插件页面：

```bat
run_daily_workflow.bat -Date 2026-05-26 -SkipScrape -NoStartPluginTask
```

### 5.6 要求 input.xlsx 必须是今天更新

如果希望避免误用旧输入文件：

```bat
run_daily_workflow.bat -RequireInputToday
```

### 5.7 指定插件开始按钮选择器

如果自动点击开始失败，查看日志和截图后，可以手动指定按钮选择器：

```bat
run_daily_workflow.bat -Date 2026-05-26 -SkipScrape -PluginStartSelector "button:has-text('开始')"
```

也可以直接调用 Python 插件上传脚本测试：

```bat
python extension_batch_upload.py --csv data\backlinks_merged_2026-05-26.csv --start-selector "button:has-text('开始')"
```

## 6. 参数说明

`daily_workflow.ps1` 支持以下常用参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `-Date` | 今天 | 工作流日期，格式 `YYYY-MM-DD`。 |
| `-DebugPort` | `9222` | Chrome 远程调试端口。 |
| `-PluginUrl` | 插件批量页 | 插件页面地址。 |
| `-PluginOptionsUrl` | 插件设置页 | 用于点击“打开批量处理”的入口页面地址。 |
| `-PluginOutputDir` | `data\output` | 插件结果 CSV 保存目录。 |
| `-PluginCompletionTimeoutMinutes` | `240` | 等待插件批量任务完成的最长时间。 |
| `-NoExportPluginResult` | 关闭 | 只启动插件任务，不等待完成、不导出结果。 |
| `-ScrapeTimeoutMinutes` | `240` | 抓取流程最大等待分钟数。 |
| `-SkipScrape` | 关闭 | 跳过网站抓取，只执行合并和插件上传。 |
| `-SkipPlugin` | 关闭 | 跳过插件上传。 |
| `-NoStartPluginTask` | 关闭 | 上传 CSV 后不点击开始按钮。 |
| `-RequireInputToday` | 关闭 | 要求 `input.xlsx` 必须是当天修改。 |
| `-CsvPath` | 合并后的当天 CSV | 手动指定上传给插件的 CSV。 |
| `-PluginStartSelector` | 自动匹配 | 手动指定插件开始按钮选择器。 |

## 7. 日志和排错

### 7.1 日志位置

每次运行会追加写入：

```text
logs\daily_workflow_YYYY-MM-DD.log
```

如果插件页面找不到文件输入框或开始按钮，会额外截图到：

```text
logs\screenshots\
```

### 7.2 Chrome debug 启动失败

检查：

1. Chrome 是否安装在：

   ```text
   C:\Program Files\Google\Chrome\Application\chrome.exe
   ```

2. 端口 `9222` 是否被其他程序占用。
3. 手动运行 `start_chrome_debug.bat` 后，浏览器是否能正常打开。
4. 是否能访问：

   ```text
   http://127.0.0.1:9222/json/version
   ```

### 7.3 插件打不开

常见原因：

1. 插件没有安装在 `browser\data` 这个自动化 profile 中。
2. 插件 ID 变化了。
3. 插件页面地址不是 `batch.html`。
4. Chrome 返回 `ERR_BLOCKED_BY_CLIENT`，通常表示当前 debug profile 没有安装或启用这个扩展 ID。

解决方式：

1. 运行 `start_chrome_debug.bat`。
2. 在打开的 Chrome 窗口中检查插件是否存在。
3. 手动访问：

   ```text
   chrome-extension://jhbjiamgmbmidfbdhflajegdkejianfl/batch.html
   ```

4. 如果页面显示“此页面已被 Chrome 屏蔽 / ERR_BLOCKED_BY_CLIENT”，需要在这个 debug Chrome 窗口里安装或启用目标插件，而不是只在日常 Chrome profile 里安装。

当前脚本会把这种情况记录为：

```json
{"message":"Extension page blocked by Chrome","extension_id":"jhbjiamgmbmidfbdhflajegdkejianfl"}
```

这会让工作流失败退出，避免误报“完成成功”。

### 7.4 插件能打开但无法上传

可能原因：

1. 插件页面没有标准 `input[type="file"]`。
2. 上传控件在 Shadow DOM 中。
3. 页面需要先点击某个按钮才出现上传框。

处理方式：

1. 先用：

   ```bat
   run_daily_workflow.bat -SkipScrape -NoStartPluginTask
   ```

2. 查看截图和日志。
3. 如需定制上传逻辑，修改 `extension_batch_upload.py` 的文件输入定位逻辑。

### 7.5 插件上传成功但无法点击开始

日志会输出类似：

```json
{"message":"No start button matched","clickables":[...]}
```

从 `clickables` 中找到正确按钮文本，然后使用：

```bat
run_daily_workflow.bat -SkipScrape -PluginStartSelector "button:has-text('按钮文字')"
```

## 8. Windows 任务计划程序建议

如果要每天定时运行，可以使用 Windows 任务计划程序：

1. 新建任务。
2. 触发器选择每天固定时间。
3. 操作选择启动程序：

   ```text
   F:\autoBackLine\autoBackLine\run_daily_workflow.bat
   ```

4. 起始于填写：

   ```text
   F:\autoBackLine\autoBackLine
   ```

5. 建议勾选“仅当用户登录时运行”，因为流程需要真实 Chrome 窗口和插件页面。

如果 `input.xlsx` 每天由人工更新，建议任务时间放在人工更新之后，或者运行时加：

```text
-RequireInputToday
```

## 9. 维护建议

1. 定期清理 `logs` 和过旧的 `data\downloads` 文件。
2. 不要频繁更换 Chrome profile，否则登录态和插件安装状态会丢失。
3. 如果插件更新导致页面按钮或上传控件变化，优先调整 `extension_batch_upload.py`。
4. 如果网站导出文件命名规则变化，优先调整 `daily_workflow.ps1` 中的 `backlinks_export_$Date*.csv` 匹配规则。
5. `config.py` 里包含登录凭据，建议只保存在本机，不要提交到公共仓库。

## 10. 推荐的首次验证步骤

第一次不要直接跑全流程，建议按以下顺序验证：

1. 验证 Chrome debug 和插件是否可用：

   ```bat
   start_chrome_debug.bat
   ```

2. 手动打开插件批量页，确认插件存在。
3. 用已有合并 CSV 测试上传但不点击开始：

   ```bat
   run_daily_workflow.bat -Date 2026-05-25 -SkipScrape -NoStartPluginTask
   ```

4. 确认上传正常后，再测试自动点击开始：

   ```bat
   run_daily_workflow.bat -Date 2026-05-25 -SkipScrape
   ```

5. 最后再运行完整流程：

   ```bat
   run_daily_workflow.bat
   ```
