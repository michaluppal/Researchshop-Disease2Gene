/**
 * afterPack hook — strips macOS extended attributes (resource forks, quarantine flags,
 * Finder metadata) from the assembled app bundle before electron-builder attempts
 * code signing. Without this, codesign fails with:
 *   "resource fork, Finder information, or similar detritus not allowed"
 */
const { execSync } = require('child_process')

module.exports = async function afterPack(context) {
  const platform = context.packager.platform.name
  if (platform !== 'mac') return

  const appOutDir = context.appOutDir
  console.log(`[afterPack] Stripping extended attributes from: ${appOutDir}`)
  try {
    execSync(`xattr -cr "${appOutDir}"`, { stdio: 'inherit' })
    console.log('[afterPack] xattr -cr completed successfully')
  } catch (err) {
    console.warn(`[afterPack] xattr -cr failed (non-fatal): ${err.message}`)
  }
}
