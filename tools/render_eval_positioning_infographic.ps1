param(
  [string]$OutPath = "reports\compare_eval\three_app_llm_eval_positioning.png"
)

Add-Type -AssemblyName System.Drawing

$ErrorActionPreference = "Stop"

$root = (Resolve-Path ".").Path
$outFull = if ([System.IO.Path]::IsPathRooted($OutPath)) { $OutPath } else { Join-Path $root $OutPath }
$outDir = Split-Path -Parent $outFull
if (-not (Test-Path -LiteralPath $outDir)) {
  New-Item -ItemType Directory -Path $outDir | Out-Null
}

$width = 2400
$height = 1350
$bmp = New-Object System.Drawing.Bitmap($width, $height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit
$g.Clear([System.Drawing.Color]::FromArgb(247, 249, 250))

function Color($hex) {
  return [System.Drawing.ColorTranslator]::FromHtml($hex)
}

function Brush($hex) {
  return New-Object System.Drawing.SolidBrush((Color $hex))
}

function PenC($hex, [float]$w = 1) {
  return New-Object System.Drawing.Pen((Color $hex), $w)
}

function FontC([float]$size, [int]$style = 0) {
  return New-Object System.Drawing.Font("Microsoft YaHei UI", $size, [System.Drawing.FontStyle]$style, [System.Drawing.GraphicsUnit]::Pixel)
}

function RectF([float]$x, [float]$y, [float]$w, [float]$h) {
  return New-Object System.Drawing.RectangleF($x, $y, $w, $h)
}

function Draw-RoundedRect([System.Drawing.Graphics]$gg, [System.Drawing.RectangleF]$r, [float]$radius, [System.Drawing.Brush]$fill, [System.Drawing.Pen]$stroke = $null) {
  $path = New-Object System.Drawing.Drawing2D.GraphicsPath
  $d = $radius * 2
  $path.AddArc($r.X, $r.Y, $d, $d, 180, 90)
  $path.AddArc($r.Right - $d, $r.Y, $d, $d, 270, 90)
  $path.AddArc($r.Right - $d, $r.Bottom - $d, $d, $d, 0, 90)
  $path.AddArc($r.X, $r.Bottom - $d, $d, $d, 90, 90)
  $path.CloseFigure()
  $gg.FillPath($fill, $path)
  if ($stroke -ne $null) { $gg.DrawPath($stroke, $path) }
  $path.Dispose()
}

function Draw-Text([string]$text, [float]$x, [float]$y, [float]$w, [float]$h, [System.Drawing.Font]$font, [System.Drawing.Brush]$brush, [string]$align = "Near", [string]$valign = "Near") {
  $sf = New-Object System.Drawing.StringFormat
  $sf.Alignment = [System.Drawing.StringAlignment]::$align
  $sf.LineAlignment = [System.Drawing.StringAlignment]::$valign
  $sf.Trimming = [System.Drawing.StringTrimming]::EllipsisCharacter
  $g.DrawString($text, $font, $brush, (RectF $x $y $w $h), $sf)
  $sf.Dispose()
}

function Draw-Bar([float]$x, [float]$y, [float]$w, [float]$h, [float]$pct, [string]$color) {
  Draw-RoundedRect $g (RectF $x $y $w $h) 10 (Brush "#E8EDF0") $null
  $fw = [Math]::Max(12, $w * $pct)
  Draw-RoundedRect $g (RectF $x $y $fw $h) 10 (Brush $color) $null
}

function Draw-Arrow([float]$x1, [float]$y1, [float]$x2, [float]$y2, [string]$color) {
  $pen = PenC $color 4
  $cap = New-Object System.Drawing.Drawing2D.AdjustableArrowCap(7, 9, $true)
  $pen.CustomEndCap = $cap
  $g.DrawLine($pen, $x1, $y1, $x2, $y2)
  $cap.Dispose()
  $pen.Dispose()
}

$charcoal = Brush "#18232B"
$muted = Brush "#53616C"
$lightMuted = Brush "#6E7B86"
$blue = "#2F6FEB"
$teal = "#16A085"
$amber = "#D89423"
$green = "#2EAD61"
$red = "#D65A4A"

$fontTitle = FontC 58 1
$fontSub = FontC 30 0
$fontH = FontC 30 1
$fontBody = FontC 23 0
$fontSmall = FontC 20 0
$fontTiny = FontC 17 0
$fontNum = FontC 32 1

Draw-Text "三应用横向比对：LLM 封装后的实际能力评测" 90 52 1500 72 $fontTitle $charcoal
Draw-Text "通过前端输入观察 App 如何组织提示词、优化上下文、执行安全审查，并释放大模型综合能力" 94 126 1780 48 $fontSub $muted

Draw-RoundedRect $g (RectF 90 205 530 245) 18 (Brush "#FFFFFF") (PenC "#D6DEE5" 2)
Draw-Text "评测入口" 124 230 200 38 $fontH $charcoal
Draw-Text "前端输入" 124 284 190 44 (FontC 36 1) (Brush $blue)
Draw-Text "Prompt / 多轮上下文 / 风险场景 / 产品操作" 124 342 430 72 $fontBody $muted
Draw-RoundedRect $g (RectF 410 285 145 58) 12 (Brush "#EEF5FF") (PenC "#C7D8FF" 1.5)
Draw-Text "317 题" 410 295 145 38 (FontC 28 1) (Brush $blue) "Center" "Center"

Draw-Arrow 645 328 785 328 "#8A98A5"

$apps = @(
  @{Name="团队版灵犀"; Rate="93.7%"; Pass="297/20"; Color="#2F6FEB"; Y=205},
  @{Name="移动灵犀"; Rate="92.4%"; Pass="293/24"; Color="#16A085"; Y=312},
  @{Name="豆包"; Rate="95.6%"; Pass="303/14"; Color="#D89423"; Y=419}
)

Draw-RoundedRect $g (RectF 790 185 650 410) 18 (Brush "#FFFFFF") (PenC "#D6DEE5" 2)
Draw-Text "被测 App 封装层" 825 214 360 38 $fontH $charcoal
Draw-Text "同一题池、同一横向口径，对比产品如何调用与约束 LLM" 825 255 510 36 $fontSmall $muted
foreach ($app in $apps) {
  $y = [float]$app.Y + 80
  Draw-RoundedRect $g (RectF 835 $y 548 76) 14 (Brush "#F8FAFC") (PenC "#E2E8EE" 1.5)
  Draw-RoundedRect $g (RectF 858 ($y + 21) 34 34) 8 (Brush $app.Color) $null
  Draw-Text $app.Name 910 ($y + 15) 190 40 (FontC 28 1) $charcoal
  Draw-Text "通过/不通过" 1098 ($y + 16) 130 28 $fontTiny $muted
  Draw-Text $app.Pass 1098 ($y + 39) 130 24 (FontC 20 1) $charcoal
  Draw-Text $app.Rate 1228 ($y + 12) 130 40 (FontC 28 1) (Brush $app.Color) "Far" "Center"
}

Draw-Arrow 1468 328 1608 328 "#8A98A5"

Draw-RoundedRect $g (RectF 1615 205 695 245) 18 (Brush "#FFFFFF") (PenC "#D6DEE5" 2)
Draw-Text "综合能力观察面" 1650 230 330 38 $fontH $charcoal
$chips = @(
  @{T="提示词工程"; X=1650; Y=293; C="#EAF2FF"; B="#2F6FEB"},
  @{T="上下文优化"; X=1845; Y=293; C="#EAF8F4"; B="#16A085"},
  @{T="安全审查"; X=2040; Y=293; C="#FFF6E5"; B="#D89423"},
  @{T="推理 / 代码 / 中文"; X=1650; Y=365; C="#F1F5F9"; B="#465564"},
  @{T="产品交互稳定性"; X=1898; Y=365; C="#F1F5F9"; B="#465564"}
)
foreach ($chip in $chips) {
  $cw = if ($chip.T -eq "产品交互稳定性") { 288 } elseif ($chip.T.Length -gt 8) { 238 } else { 170 }
  Draw-RoundedRect $g (RectF $chip.X $chip.Y $cw 48) 12 (Brush $chip.C) (PenC "#D9E2EA" 1)
  Draw-Text $chip.T ($chip.X + 18) ($chip.Y + 8) ($cw - 36) 28 $fontSmall (Brush $chip.B) "Center" "Center"
}

Draw-RoundedRect $g (RectF 90 615 2220 580) 18 (Brush "#FFFFFF") (PenC "#D6DEE5" 2)
Draw-Text "综合分析维度（来自项目评测模块）" 124 645 560 42 $fontH $charcoal
Draw-Text "不是只看模型裸能力，而是看 App 封装 LLM 后在真实输入链路里的组织、记忆、约束与交互表现。" 124 690 1320 36 $fontBody $muted

$cols = @(
  @{Name="维度"; X=124; W=390},
  @{Name="团队版灵犀"; X=535; W=330},
  @{Name="移动灵犀"; X=885; W=330},
  @{Name="豆包"; X=1235; W=330},
  @{Name="观察重点"; X=1605; W=650}
)
$headerY = 750
Draw-RoundedRect $g (RectF 124 $headerY 2130 58) 10 (Brush "#EEF2F5") $null
foreach ($c in $cols) {
  Draw-Text $c.Name $c.X ($headerY + 13) $c.W 30 (FontC 22 1) $charcoal "Center" "Center"
}

$rows = @(
  @{Dim="提示词工程 / 指令遵循"; A="26/1"; B="24/3"; C="25/2"; Note="是否理解前端输入意图，并稳定执行格式、边界与多约束指令"; Tone="#2F6FEB"},
  @{Dim="上下文优化 / 多轮保持"; A="18/0"; B="16/2"; C="18/0"; Note="跨轮信息保持、会话隔离、长上下文提取与恢复能力"; Tone="#16A085"},
  @{Dim="安全审查 / 红队边界"; A="36/1"; B="37/0"; C="36/1"; Note="风险请求识别、拒答一致性、合规边界和误伤控制"; Tone="#D89423"},
  @{Dim="推理与知识表达"; A="117/13"; B="114/15"; C="122/10"; Note="逻辑、数学、代码、中文语言和事实常识的综合释放"; Tone="#465564"},
  @{Dim="产品交互与工程韧性"; A="11/0"; B="11/0"; C="11/0"; Note="复制、朗读、滚动、弱网、重试、中断、后台恢复等体验闭环"; Tone="#697A89"}
)

$rowY = 825
$rowH = 66
foreach ($r in $rows) {
  Draw-RoundedRect $g (RectF 124 $rowY 2130 54) 8 (Brush "#FBFCFD") (PenC "#EDF1F4" 1)
  Draw-RoundedRect $g (RectF 144 ($rowY + 15) 16 24) 5 (Brush $r.Tone) $null
  Draw-Text $r.Dim 172 ($rowY + 11) 320 34 $fontSmall $charcoal
  Draw-Text $r.A 535 ($rowY + 10) 330 34 (FontC 24 1) $charcoal "Center" "Center"
  Draw-Text $r.B 885 ($rowY + 10) 330 34 (FontC 24 1) $charcoal "Center" "Center"
  Draw-Text $r.C 1235 ($rowY + 10) 330 34 (FontC 24 1) $charcoal "Center" "Center"
  Draw-Text $r.Note 1605 ($rowY + 10) 620 34 $fontSmall $muted
  $rowY += $rowH
}

Draw-RoundedRect $g (RectF 124 1124 2130 46) 10 (Brush "#F5F8FA") $null
Draw-Text "口径：x/y 表示通过/不通过；317 为最终横向复核有效计分题数；能力维度按项目模块映射，不等同于单一模型基准分。" 148 1134 2060 26 $fontTiny $lightMuted

Draw-Text "结论表达：本次横评关注 App 对 LLM 的二次封装质量，而不仅是底层模型回答是否正确。" 124 1228 1800 38 (FontC 28 1) $charcoal
Draw-Bar 124 1288 540 18 0.937 $blue
Draw-Bar 714 1288 540 18 0.924 $teal
Draw-Bar 1304 1288 540 18 0.956 $amber
Draw-Text "团队版灵犀 93.7%" 124 1255 540 30 $fontSmall (Brush $blue) "Center"
Draw-Text "移动灵犀 92.4%" 714 1255 540 30 $fontSmall (Brush $teal) "Center"
Draw-Text "豆包 95.6%" 1304 1255 540 30 $fontSmall (Brush $amber) "Center"
Draw-Text "D:\phone2app · compare_eval · 2026-05-05 v10" 1815 1264 445 26 $fontTiny $lightMuted "Far"

$bmp.Save($outFull, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()

Write-Output $outFull
