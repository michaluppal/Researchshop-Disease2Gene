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

function writeIco(pngPaths, output) {
  const images = pngPaths.map((path) => {
    const match = path.match(/-(\d+)\.png$/)
    if (!match) throw new Error(`Cannot infer ICO size from ${path}`)
    return { size: Number(match[1]), data: readFileSync(path) }
  })

  const header = Buffer.alloc(6)
  header.writeUInt16LE(0, 0)
  header.writeUInt16LE(1, 2)
  header.writeUInt16LE(images.length, 4)

  let offset = 6 + images.length * 16
  const entries = images.map(({ size, data }) => {
    const entry = Buffer.alloc(16)
    entry.writeUInt8(size === 256 ? 0 : size, 0)
    entry.writeUInt8(size === 256 ? 0 : size, 1)
    entry.writeUInt8(0, 2)
    entry.writeUInt8(0, 3)
    entry.writeUInt16LE(1, 4)
    entry.writeUInt16LE(32, 6)
    entry.writeUInt32LE(data.length, 8)
    entry.writeUInt32LE(offset, 12)
    offset += data.length
    return entry
  })

  writeFileSync(output, Buffer.concat([header, ...entries, ...images.map(({ data }) => data)]))
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

  const icoSizes = [16, 24, 32, 48, 64, 128, 256]
  const icoPngs = icoSizes.map((size) => {
    const output = join(tmp, `ico-${size}.png`)
    renderIconPng(baseIconPng, size, output)
    return output
  })
  writeIco(icoPngs, join(resourcesDir, 'icon.ico'))

  generateDmgBackgrounds(tmp)

  console.log('Generated ResearchShop brand assets from app/resources/icon-source.svg')
} finally {
  rmSync(tmp, { recursive: true, force: true })
}
