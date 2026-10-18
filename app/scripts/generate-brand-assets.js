const { execFileSync } = require('node:child_process')
const { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } = require('node:fs')
const { basename, join, resolve } = require('node:path')

const repoRoot = resolve(__dirname, '../..')
const resourcesDir = join(repoRoot, 'app/resources')
const sourceSvg = join(resourcesDir, 'icon-source.svg')

function run(command, args) {
  execFileSync(command, args, { stdio: 'inherit' })
}

function renderSvg(input, size, output) {
  const renderDir = mkdtempSync('/private/tmp/researchshop-render-')
  try {
    run('qlmanage', ['-t', '-s', String(size), '-o', renderDir, input])
    copyFileSync(join(renderDir, `${basename(input)}.png`), output)
  } finally {
    rmSync(renderDir, { recursive: true, force: true })
  }
}

function resizePng(input, width, height, output) {
  run('sips', ['-z', String(height), String(width), input, '--out', output])
}

function renderIconPng(basePng, size, output) {
  resizePng(basePng, size, size, output)
}

function generateDmgBackgrounds(workDir) {
  const swiftPath = join(workDir, 'generate-dmg-background.swift')
  const rawBackground = join(workDir, 'dmg-background-raw.png')
  const rawBackground2x = join(workDir, 'dmg-background-raw@2x.png')
  writeFileSync(swiftPath, `
import AppKit

let resourcesDir = CommandLine.arguments[1]
let outputPath = CommandLine.arguments[2]
let outputPath2x = CommandLine.arguments[3]
let logicalWidth: CGFloat = 660
let logicalHeight: CGFloat = 400

func color(_ hex: Int, alpha: CGFloat = 1) -> NSColor {
  let red = CGFloat((hex >> 16) & 0xff) / 255
  let green = CGFloat((hex >> 8) & 0xff) / 255
  let blue = CGFloat(hex & 0xff) / 255
  return NSColor(calibratedRed: red, green: green, blue: blue, alpha: alpha)
}

func drawBackground(scale: CGFloat, output: String) throws {
  let size = NSSize(width: logicalWidth * scale, height: logicalHeight * scale)
  let image = NSImage(size: size)
  image.lockFocus()
  NSGraphicsContext.current?.imageInterpolation = .high

  func rect(_ x: CGFloat, _ top: CGFloat, _ width: CGFloat, _ height: CGFloat) -> NSRect {
    NSRect(x: x * scale, y: (logicalHeight - top - height) * scale, width: width * scale, height: height * scale)
  }

  func point(_ x: CGFloat, _ top: CGFloat) -> NSPoint {
    NSPoint(x: x * scale, y: (logicalHeight - top) * scale)
  }

  func rounded(_ x: CGFloat, _ top: CGFloat, _ width: CGFloat, _ height: CGFloat, _ radius: CGFloat, fill: NSColor, stroke: NSColor? = nil) {
    let path = NSBezierPath(roundedRect: rect(x, top, width, height), xRadius: radius * scale, yRadius: radius * scale)
    fill.setFill()
    path.fill()
    if let stroke = stroke {
      stroke.setStroke()
      path.lineWidth = scale
      path.stroke()
    }
  }

  func text(_ value: String, _ x: CGFloat, _ top: CGFloat, _ width: CGFloat, _ height: CGFloat, size fontSize: CGFloat, weight: NSFont.Weight, fill: NSColor) {
    let attributes: [NSAttributedString.Key: Any] = [
      .font: NSFont.systemFont(ofSize: fontSize * scale, weight: weight),
      .foregroundColor: fill
    ]
    NSString(string: value).draw(in: rect(x, top, width, height), withAttributes: attributes)
  }

  color(0xF8FAFC).setFill()
  NSRect(origin: .zero, size: size).fill()
  rounded(54, 42, 552, 316, 28, fill: .white, stroke: color(0xE2E8F0))
  rounded(88, 136, 124, 124, 32, fill: color(0xDBEAFE))
  rounded(448, 136, 124, 124, 32, fill: color(0xF1F5F9), stroke: color(0xCBD5E1))

  if let icon = NSImage(contentsOfFile: resourcesDir + "/icon.png") {
    icon.draw(in: rect(105, 153, 90, 90), from: .zero, operation: .sourceOver, fraction: 1)
  }

  let arrow = NSBezierPath()
  arrow.move(to: point(250, 200))
  arrow.line(to: point(407, 200))
  color(0x2563EB).setStroke()
  arrow.lineWidth = 4 * scale
  arrow.lineCapStyle = .round
  arrow.stroke()

  let head = NSBezierPath()
  head.move(to: point(407, 200))
  head.line(to: point(383, 184))
  head.line(to: point(383, 216))
  head.close()
  color(0x2563EB).setFill()
  head.fill()

  text("ResearchShop", 106, 282, 120, 24, size: 13, weight: .semibold, fill: color(0x64748B))
  text("Applications", 464, 282, 120, 24, size: 13, weight: .semibold, fill: color(0x64748B))
  text("Drag ResearchShop to Applications", 204, 304, 340, 28, size: 14, weight: .semibold, fill: color(0x475569))

  image.unlockFocus()

  guard
    let tiff = image.tiffRepresentation,
    let bitmap = NSBitmapImageRep(data: tiff),
    let png = bitmap.representation(using: .png, properties: [:])
  else {
    throw NSError(domain: "ResearchShopBrandAssets", code: 1, userInfo: [NSLocalizedDescriptionKey: "Could not encode DMG background PNG"])
  }
  try png.write(to: URL(fileURLWithPath: output))
}

try drawBackground(scale: 1, output: outputPath)
try drawBackground(scale: 2, output: outputPath2x)
`)
  run('swift', [swiftPath, resourcesDir, rawBackground, rawBackground2x])
  resizePng(rawBackground, 660, 400, join(resourcesDir, 'dmg-background.png'))
  resizePng(rawBackground2x, 1320, 800, join(resourcesDir, 'dmg-background@2x.png'))
}

function writeWindowsBrand(basePng, workDir) {
  const swiftPath = join(workDir, 'generate-windows-brand.swift')
  writeFileSync(swiftPath, `
import AppKit

let sourcePath = CommandLine.arguments[1]
let icoPath = CommandLine.arguments[2]
let sidebarPath = CommandLine.arguments[3]
let sizes = [16, 24, 32, 48, 64, 128, 256]

guard let source = NSImage(contentsOfFile: sourcePath) else {
  fputs("Could not read \\(sourcePath)\\n", stderr)
  exit(1)
}

func color(_ hex: Int) -> NSColor {
  NSColor(
    calibratedRed: CGFloat((hex >> 16) & 0xff) / 255,
    green: CGFloat((hex >> 8) & 0xff) / 255,
    blue: CGFloat(hex & 0xff) / 255,
    alpha: 1
  )
}

func bitmap(_ width: Int, _ height: Int, draw: (NSRect) -> Void) -> NSBitmapImageRep {
  guard let rep = NSBitmapImageRep(
    bitmapDataPlanes: nil,
    pixelsWide: width,
    pixelsHigh: height,
    bitsPerSample: 8,
    samplesPerPixel: 4,
    hasAlpha: true,
    isPlanar: false,
    colorSpaceName: .deviceRGB,
    bitmapFormat: [.thirtyTwoBitLittleEndian],
    bytesPerRow: width * 4,
    bitsPerPixel: 32
  ) else {
    fputs("Could not allocate bitmap\\n", stderr)
    exit(1)
  }
  NSGraphicsContext.saveGraphicsState()
  NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
  NSGraphicsContext.current?.imageInterpolation = .high
  draw(NSRect(x: 0, y: 0, width: width, height: height))
  NSGraphicsContext.restoreGraphicsState()
  return rep
}

func dibImage(_ size: Int) -> Data {
  let rep = bitmap(size, size) { rect in
    NSColor.clear.setFill()
    rect.fill()
    source.draw(in: rect, from: .zero, operation: .sourceOver, fraction: 1)
  }
  let pixels = rep.bitmapData!
  var xor = Data()
  xor.reserveCapacity(size * size * 4)
  for y in stride(from: size - 1, through: 0, by: -1) {
    for x in 0..<size {
      let i = (y * size + x) * 4
      let r = Int(pixels[i])
      let g = Int(pixels[i + 1])
      let b = Int(pixels[i + 2])
      let a = Int(pixels[i + 3])
      // AppKit stores premultiplied BGRA in this format. Windows icons want straight alpha.
      let scale = a == 0 ? 0 : 255
      let bb = UInt8(a == 0 ? 0 : min(255, b * scale / a))
      let gg = UInt8(a == 0 ? 0 : min(255, g * scale / a))
      let rr = UInt8(a == 0 ? 0 : min(255, r * scale / a))
      xor.append(contentsOf: [bb, gg, rr, UInt8(a)])
    }
  }
  let maskStride = ((size + 31) / 32) * 4
  let mask = Data(count: maskStride * size)
  var header = Data(count: 40)
  header.replaceSubrange(0..<4, with: le32(40))
  header.replaceSubrange(4..<8, with: le32(size))
  header.replaceSubrange(8..<12, with: le32(size * 2))
  header.replaceSubrange(12..<14, with: le16(1))
  header.replaceSubrange(14..<16, with: le16(32))
  let imageSize = xor.count + mask.count
  header.replaceSubrange(20..<24, with: le32(imageSize))
  return header + xor + mask
}

func le16(_ value: Int) -> Data {
  var v = UInt16(value).littleEndian
  return Data(bytes: &v, count: 2)
}

func le32(_ value: Int) -> Data {
  var v = UInt32(value).littleEndian
  return Data(bytes: &v, count: 4)
}

let images = sizes.map { dibImage($0) }
var ico = Data()
ico.append(contentsOf: le16(0))
ico.append(contentsOf: le16(1))
ico.append(contentsOf: le16(sizes.count))
var offset = 6 + sizes.count * 16
for (size, image) in zip(sizes, images) {
  let dim = size == 256 ? 0 : size
  ico.append(UInt8(dim))
  ico.append(UInt8(dim))
  ico.append(0)
  ico.append(0)
  ico.append(contentsOf: le16(1))
  ico.append(contentsOf: le16(32))
  ico.append(contentsOf: le32(image.count))
  ico.append(contentsOf: le32(offset))
  offset += image.count
}
for image in images {
  ico.append(image)
}
try ico.write(to: URL(fileURLWithPath: icoPath))

let sidebarWidth = 164
let sidebarHeight = 314
let sidebar = bitmap(sidebarWidth, sidebarHeight) { rect in
  let gradient = NSGradient(colors: [color(0x2563EB), color(0x14B8A6)])
  gradient?.draw(in: rect, angle: -90)
  let iconSize: CGFloat = 108
  let iconRect = NSRect(
    x: (CGFloat(sidebarWidth) - iconSize) / 2,
    y: 118,
    width: iconSize,
    height: iconSize
  )
  source.draw(in: iconRect, from: .zero, operation: .sourceOver, fraction: 1)
  let title = "ResearchShop" as NSString
  let attrs: [NSAttributedString.Key: Any] = [
    .font: NSFont.systemFont(ofSize: 16, weight: .semibold),
    .foregroundColor: NSColor.white
  ]
  let titleSize = title.size(withAttributes: attrs)
  title.draw(
    at: NSPoint(x: (CGFloat(sidebarWidth) - titleSize.width) / 2, y: 86),
    withAttributes: attrs
  )
}
guard
  let tiff = sidebar.tiffRepresentation,
  let opaque = NSBitmapImageRep(data: tiff),
  let png = opaque.representation(using: .png, properties: [:])
else {
  fputs("Could not encode installer sidebar\\n", stderr)
  exit(1)
}
let sidebarPixels = sidebar.bitmapData!
var bmpPixels = Data()
let rowBytes = ((sidebarWidth * 3 + 3) / 4) * 4
for y in stride(from: sidebarHeight - 1, through: 0, by: -1) {
  var row = Data()
  for x in 0..<sidebarWidth {
    let i = (y * sidebarWidth + x) * 4
    row.append(sidebarPixels[i + 2])
    row.append(sidebarPixels[i + 1])
    row.append(sidebarPixels[i])
  }
  row.append(Data(count: rowBytes - sidebarWidth * 3))
  bmpPixels.append(row)
}
let pixelBytes = bmpPixels.count
var bmp = Data()
bmp.append(contentsOf: [0x42, 0x4d])
bmp.append(contentsOf: le32(54 + pixelBytes))
bmp.append(contentsOf: le16(0))
bmp.append(contentsOf: le16(0))
bmp.append(contentsOf: le32(54))
bmp.append(contentsOf: le32(40))
bmp.append(contentsOf: le32(sidebarWidth))
bmp.append(contentsOf: le32(sidebarHeight))
bmp.append(contentsOf: le16(1))
bmp.append(contentsOf: le16(24))
bmp.append(contentsOf: le32(0))
bmp.append(contentsOf: le32(pixelBytes))
bmp.append(contentsOf: le32(2835))
bmp.append(contentsOf: le32(2835))
bmp.append(contentsOf: le32(0))
bmp.append(contentsOf: le32(0))
bmp.append(bmpPixels)
try bmp.write(to: URL(fileURLWithPath: sidebarPath))
`)
  run('swift', [
    swiftPath,
    basePng,
    join(resourcesDir, 'icon.ico'),
    join(resourcesDir, 'installer-sidebar.bmp'),
  ])
}

const tmp = mkdtempSync('/private/tmp/researchshop-brand-')

try {
  const baseIconPng = join(tmp, 'icon-base.png')
  renderSvg(sourceSvg, 1024, baseIconPng)

  const iconset = join(tmp, 'ResearchShop.iconset')
  mkdirSync(iconset, { recursive: true })

  const iconsetSizes = [
    ['icon_16x16.png', 16],
    ['icon_16x16@2x.png', 32],
    ['icon_32x32.png', 32],
    ['icon_32x32@2x.png', 64],
    ['icon_128x128.png', 128],
    ['icon_128x128@2x.png', 256],
    ['icon_256x256.png', 256],
    ['icon_256x256@2x.png', 512],
    ['icon_512x512.png', 512],
    ['icon_512x512@2x.png', 1024],
  ]
  for (const [name, size] of iconsetSizes) {
    renderIconPng(baseIconPng, size, join(iconset, name))
  }
  run('iconutil', ['-c', 'icns', iconset, '-o', join(resourcesDir, 'icon.icns')])

  renderIconPng(baseIconPng, 1024, join(resourcesDir, 'icon.png'))
  writeWindowsBrand(join(resourcesDir, 'icon.png'), tmp)

  if (!process.argv.includes('--windows-icons')) generateDmgBackgrounds(tmp)

  console.log('Generated ResearchShop brand assets from app/resources/icon-source.svg')
} finally {
  rmSync(tmp, { recursive: true, force: true })
}
