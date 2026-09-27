"""依据当前源码绘制正方形流程图；不导入或执行设备测试代码。

运行：python 功耗测试流水线架构图_生成脚本.py
依赖：Pillow。输出：SVG、3200px PNG、可编辑 draw.io 文件。
"""
from pathlib import Path
import math
import xml.etree.ElementTree as ET
from html import escape
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "流程图交付"
OUT.mkdir(exist_ok=True)
NAME = "功耗自动化测试流水线"
SIZE = 1600
SCALE = 2
FONT = Path("C:/Windows/Fonts/msyh.ttc")
BOLD = Path("C:/Windows/Fonts/msyhbd.ttc")
INK = "#172D46"
MUTED = "#41566F"
BLUE = "#356CAB"
TEAL = "#227C78"
PURPLE = "#7460A4"
LINE = "#607890"
items = []


def text(x, y, value, size=26, bold=False, color=INK, anchor="middle"):
    items.append(dict(kind="text", x=x, y=y, value=value, size=size,
                      bold=bold, color=color, anchor=anchor))


def shape(id_, x, y, w, h, fill, stroke, kind="rect", radius=12):
    items.append(dict(kind=kind, id=id_, x=x, y=y, w=w, h=h,
                      fill=fill, stroke=stroke, radius=radius))


def box(id_, x, y, w, h, title, lines, color=BLUE, fill="#F0F5FC"):
    shape(id_, x, y, w, h, fill, color)
    total = 37 + len(lines) * 33
    top = y + (h-total)/2
    text(x+w/2, top+18, title, 32, True)
    for i, line in enumerate(lines):
        text(x+w/2, top+54+i*33, line, 25, False, MUTED)


def arrow(points, color=LINE, dashed=False, source=None, target=None):
    items.append(dict(kind="arrow", points=points, color=color, dashed=dashed,
                      source=source, target=target))


def label(x, y, value, color=MUTED):
    # White label backing keeps return-line captions legible.
    w = len(value)*25+20
    shape("label-bg-"+str(len(items)), x-w/2, y-17, w, 34, "#FFFFFF", "none", radius=4)
    text(x, y, value, 25, True, color)


# Canvas and section frames.
shape("canvas", 0, 0, SIZE, SIZE, "#FFFFFF", "none", radius=0)
text(72, 79, "功耗自动化测试流水线", 54, True, anchor="start")
text(74, 133, "配置驱动  ·  多固件队列  ·  多挡位测试  ·  自动汇总", 27, color=MUTED, anchor="start")
text(76, 188, "01  启动与设备准备", 29, True, BLUE, "start")
shape("test-region", 65, 375, 1470, 843, "#FAFCFE", "#D3DFEA", radius=18)
text(90, 408, "02  逐挡位执行", 29, True, TEAL, "start")
text(90, 449, "单挡位 / 全部挡位", 25, color=MUTED, anchor="start")
text(76, 1280, "03  结果归档与通知", 29, True, PURPLE, "start")

# Flow edges, laid down before nodes.
arrow([(510, 280), (580, 280)], source="config", target="ota")
arrow([(1000, 280), (1070, 280)], source="ota", target="env")
arrow([(1280, 341), (1280, 362), (800, 362), (800, 430)], source="env", target="select")
arrow([(800, 522), (800, 548)], source="select", target="mode")
arrow([(680, 610), (305, 610), (305, 700)], source="mode", target="record")
arrow([(800, 672), (800, 700)], source="mode", target="preview")
arrow([(920, 610), (1295, 610), (1295, 700)], source="mode", target="sleep")
arrow([(305, 810), (305, 838), (680, 838), (680, 866)], source="record", target="qepm")
arrow([(800, 810), (800, 866)], source="preview", target="qepm")
arrow([(1295, 810), (1295, 838), (920, 838), (920, 866)], source="sleep", target="qepm")
arrow([(800, 970), (800, 1003)], source="qepm", target="excel")
arrow([(1150, 1058), (1240, 1058)], source="excel", target="more")
arrow([(1350, 996), (1350, 935), (1505, 935), (1505, 476), (1120, 476)],
      color=TEAL, source="more", target="select")
arrow([(1350, 1120), (1350, 1242), (475, 1242), (475, 1310)], source="more", target="cleanup")
arrow([(510, 1376), (580, 1376)], source="cleanup", target="summary")
arrow([(1000, 1376), (1070, 1376)], source="summary", target="report")

# Preparation.
box("config", 90, 220, 420, 121, "界面 / 命令行启动", ["选择设备、固件与挡位", "读取 JSON 测试配置"])
box("ota", 580, 220, 420, 121, "固件检查与 OTA", ["按需下载、升级并校验", "未配置 / 版本相同则跳过"])
box("env", 1070, 220, 420, 121, "设备环境准备", ["检查用户模式、清理视频", "配置开关、启动控制服务"])

# Per-gear loop. The first gear does not run the temperature gate.
box("select", 480, 430, 640, 92, "选择挡位 · 检查温度", ["后续挡位低于 55°C 再测；首挡跳过"], TEAL, "#EDF8F6")
shape("mode", 680, 548, 240, 124, "#EDF8F6", TEAL, kind="diamond")
text(800, 610, "测试模式", 30, True)
box("record", 105, 700, 400, 110, "录制模式", ["短录视频 → 拉取解析", "校验分辨率 / 帧率"], TEAL, "#EDF8F6")
box("preview", 600, 700, 400, 110, "预览模式", ["设置相机挡位", "保持预览，不开启录制"], TEAL, "#EDF8F6")
box("sleep", 1095, 700, 400, 110, "关机充电模式", ["进入关机充电状态", "等待设备休眠"], TEAL, "#EDF8F6")
label(459, 838, "校验通过")
box("qepm", 450, 866, 700, 104, "QEPM 自动采集功耗", ["配置通道 · 关闭 USB 供电 · 按时长采集", "停止采集 → 下载原始 CSV"], TEAL, "#EDF8F6")
box("excel", 450, 1003, 700, 110, "处理本挡位数据", ["CSV 导入 Excel 模板", "读取负载端、电池端及模块功耗"], TEAL, "#EDF8F6")
shape("more", 1240, 996, 220, 124, "#EDF8F6", TEAL, kind="diamond")
text(1350, 1058, "还有挡位？", 27, True)
label(1325, 476, "是：下一挡位", TEAL)
label(1350, 1239, "否")
text(97, 1157, "温控：每 10s 检查，最多等待 300s；超时跳过当前挡位。", 25, color=MUTED, anchor="start")
text(97, 1195, "挡位异常：记录错误，批量测试继续下一挡位；最终汇总失败状态。", 25, color=MUTED, anchor="start")

# Post-run work follows teardown in the actual script.
box("cleanup", 90, 1310, 420, 132, "结果落盘与环境恢复", ["保存结果 JSON、错误信息", "清理控制服务、关闭浏览器"], PURPLE, "#F4F1FA")
box("summary", 580, 1310, 420, 132, "汇总各挡位 Excel", ["按固件日期归档测试数据", "生成挡位表与总汇总表"], PURPLE, "#F4F1FA")
box("report", 1070, 1310, 420, 132, "飞书同步与通知", ["同步汇总文件夹", "发送功耗、状态及数据链接"], PURPLE, "#F4F1FA")
shape("queue-note", 65, 1480, 1470, 74, "#F0F4F8", "none", radius=12)
text(800, 1517, "GUI 固件队列：每个固件重复以上流程，队列结束后统计成功 / 失败", 28, True, MUTED)


def points_for(item):
    x, y, w, h = (item[k] for k in ("x", "y", "w", "h"))
    return [(x+w/2, y), (x+w, y+h/2), (x+w/2, y+h), (x, y+h/2)]


def head(points):
    x, y = points[-1]
    px, py = points[-2]
    angle = math.atan2(y-py, x-px)
    return [(x, y), (x-13*math.cos(angle)+5.5*math.sin(angle), y-13*math.sin(angle)-5.5*math.cos(angle)),
            (x-13*math.cos(angle)-5.5*math.sin(angle), y-13*math.sin(angle)+5.5*math.cos(angle))]


def write_svg():
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" viewBox="0 0 {SIZE} {SIZE}">',
           '<title>功耗自动化测试流水线</title>',
           '<desc>依据现有 Python 代码整理：配置与 OTA、逐挡位温控及模式分支、QEPM 采集、Excel 处理、归档与飞书通知。</desc>']
    for i in items:
        k = i['kind']
        if k == 'text':
            out.append(f'<text x="{i["x"]}" y="{i["y"]}" text-anchor="{i["anchor"]}" dominant-baseline="central" font-family="Microsoft YaHei, Noto Sans CJK SC, sans-serif" font-size="{i["size"]}" font-weight="{700 if i["bold"] else 400}" fill="{i["color"]}">{escape(i["value"])}</text>')
        elif k in ('rect', 'diamond'):
            common = f'fill="{i["fill"]}" stroke="{i["stroke"]}" stroke-width="2"'
            if k == 'rect':
                out.append(f'<rect x="{i["x"]}" y="{i["y"]}" width="{i["w"]}" height="{i["h"]}" rx="{i["radius"]}" {common}/>')
            else:
                coords = ' '.join(f'{x},{y}' for x,y in points_for(i))
                out.append(f'<polygon points="{coords}" {common}/>')
        else:
            coords = ' '.join(f'{x},{y}' for x,y in i['points'])
            dash = 'stroke-dasharray="9 7"' if i['dashed'] else ''
            out.append(f'<polyline points="{coords}" fill="none" stroke="{i["color"]}" stroke-width="3" stroke-linejoin="round" {dash}/>')
            coords = ' '.join(f'{x},{y}' for x,y in head(i['points']))
            out.append(f'<polygon points="{coords}" fill="{i["color"]}"/>')
    out.append('</svg>')
    (OUT / f'{NAME}.svg').write_text('\n'.join(out), encoding='utf-8')


def write_png():
    img = Image.new('RGB', (SIZE*SCALE, SIZE*SCALE), 'white')
    draw = ImageDraw.Draw(img)
    def scaled(points):
        return [(round(x*SCALE), round(y*SCALE)) for x,y in points]
    for i in items:
        k = i['kind']
        if k == 'text':
            font = ImageFont.truetype(str(BOLD if i['bold'] else FONT), round(i['size']*SCALE))
            # Center the actual ink, rather than using the CJK font's asymmetric ascender.
            bbox = draw.textbbox((0,0), i['value'], font=font)
            width, height = bbox[2]-bbox[0], bbox[3]-bbox[1]
            x = i['x']*SCALE - (width/2 if i['anchor']=='middle' else 0)
            y = i['y']*SCALE-height/2-bbox[1]
            draw.text((round(x), round(y)), i['value'], font=font, fill=i['color'])
        elif k == 'rect':
            coords = scaled([(i['x'],i['y']), (i['x']+i['w'],i['y']+i['h'])])
            draw.rounded_rectangle(coords, radius=i['radius']*SCALE, fill=i['fill'],
                                   outline=None if i['stroke']=='none' else i['stroke'], width=2*SCALE)
        elif k == 'diamond':
            pts = scaled(points_for(i))
            draw.polygon(pts, fill=i['fill'])
            draw.line(pts+[pts[0]], fill=i['stroke'], width=2*SCALE, joint='curve')
        else:
            draw.line(scaled(i['points']), fill=i['color'], width=3*SCALE, joint='curve')
            draw.polygon(scaled(head(i['points'])), fill=i['color'])
    img.save(OUT / f'{NAME}.png', dpi=(300,300))
    img.resize((1000,1000), Image.Resampling.LANCZOS).save(OUT / '预览.png')


def write_drawio():
    mx = ET.Element('mxfile', host='app.diagrams.net')
    diagram = ET.SubElement(mx, 'diagram', id='power-pipeline', name='功耗测试流水线')
    model = ET.SubElement(diagram, 'mxGraphModel', dx='1600', dy='1600', grid='1', gridSize='10',
                          page='1', pageScale='1', pageWidth='1600', pageHeight='1600', background='#FFFFFF')
    root = ET.SubElement(model, 'root')
    ET.SubElement(root, 'mxCell', id='0')
    ET.SubElement(root, 'mxCell', id='1', parent='0')
    shapes = {i.get('id'):i for i in items if i['kind'] in ('rect','diamond')}
    for index, i in enumerate(items):
        k = i['kind']
        if i.get('id') == 'canvas':
            continue
        attrs = dict(id=i.get('id', f'item-{index}'), parent='1')
        if k == 'arrow':
            style = f'edgeStyle=none;rounded=0;html=1;endArrow=block;endFill=1;strokeColor={i["color"]};strokeWidth=3;'
            points = i['points']
            attrs['edge'] = '1'
            for key, p, tag in [('source',points[0],'exit'), ('target',points[-1],'entry')]:
                if i[key]:
                    attrs[key] = i[key]
                    s = shapes[i[key]]
                    style += f'{tag}X={(p[0]-s["x"])/s["w"]};{tag}Y={(p[1]-s["y"])/s["h"]};{tag}Perimeter=0;'
            attrs['style'] = style
            cell = ET.SubElement(root, 'mxCell', **attrs)
            geo = ET.SubElement(cell, 'mxGeometry', relative='1', attrib={'as':'geometry'})
            ET.SubElement(geo, 'mxPoint', x=str(points[0][0]), y=str(points[0][1]), attrib={'as':'sourcePoint'})
            ET.SubElement(geo, 'mxPoint', x=str(points[-1][0]), y=str(points[-1][1]), attrib={'as':'targetPoint'})
            if len(points)>2:
                arr = ET.SubElement(geo, 'Array', attrib={'as':'points'})
                for x,y in points[1:-1]:
                    ET.SubElement(arr, 'mxPoint', x=str(x), y=str(y))
        else:
            attrs['vertex'] = '1'
            if k == 'text':
                w = len(i['value'])*i['size']+20
                h = i['size']*1.6
                x = i['x']-w/2 if i['anchor']=='middle' else i['x']
                y = i['y']-h/2
                attrs['value'] = i['value']
                attrs['style'] = f'text;html=0;whiteSpace=wrap;overflow=visible;align={"center" if i["anchor"]=="middle" else "left"};verticalAlign=middle;fontFamily=Microsoft YaHei;fontSize={i["size"]};fontStyle={1 if i["bold"] else 0};fontColor={i["color"]};strokeColor=none;fillColor=none;spacing=0;'
            else:
                x,y,w,h = (i[key] for key in ('x','y','w','h'))
                typ = 'rhombus;' if k=='diamond' else 'rounded=1;absoluteArcSize=1;arcSize=24;'
                attrs['style'] = f'{typ}whiteSpace=wrap;html=1;fillColor={i["fill"]};strokeColor={i["stroke"]};strokeWidth=2;'
            cell = ET.SubElement(root, 'mxCell', **attrs)
            ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y), width=str(w), height=str(h), attrib={'as':'geometry'})
    ET.indent(mx)
    ET.ElementTree(mx).write(OUT / f'{NAME}.drawio', encoding='utf-8', xml_declaration=True)


if __name__ == '__main__':
    write_svg()
    write_png()
    write_drawio()
    print(f'已生成：{OUT}')
