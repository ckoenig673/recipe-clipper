import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const appJsPath = path.resolve(process.cwd(), 'frontend/app.js');
const source = readFileSync(appJsPath, 'utf8');
const start = source.indexOf('function normalizeHostname(');
const end = source.indexOf('function getImportFallbackMessage(');

if (start === -1 || end === -1 || end <= start) {
  throw new Error('Could not locate URL hostname helper block in frontend/app.js');
}

const helperSource = `${source.slice(start, end)}
globalThis.__frontendHostnameHelpers = {
  normalizeHostname,
  hostnameMatchesDomain,
  parseHostname,
  isSocialShareUrl,
  isFacebookInternalUrl,
  isFacebookReelOrShareUrl
};`;

const sandbox = { URL, globalThis: {} };
vm.createContext(sandbox);
new vm.Script(helperSource, { filename: 'frontend/app.js' }).runInContext(sandbox);

const {
  normalizeHostname,
  hostnameMatchesDomain,
  parseHostname,
  isSocialShareUrl,
  isFacebookInternalUrl,
  isFacebookReelOrShareUrl
} = sandbox.globalThis.__frontendHostnameHelpers;

test('frontend hostname helpers accept exact domains and valid subdomains', () => {
  assert.equal(normalizeHostname('WWW.FACEBOOK.COM..'), 'www.facebook.com');
  assert.equal(hostnameMatchesDomain('m.facebook.com.', 'facebook.com'), true);
  assert.equal(isSocialShareUrl('https://sub.instagr.am:443/reel/abc?x=1#top'), true);
  assert.equal(isFacebookInternalUrl('https://video.fb.watch:8443/watch/?v=1'), true);
});

test('frontend hostname helpers reject lookalike domains', () => {
  assert.equal(isSocialShareUrl('https://facebook.com.attacker.example/reel/123'), false);
  assert.equal(isSocialShareUrl('https://attackerfacebook.com/reel/123'), false);
  assert.equal(isFacebookInternalUrl('https://fb.watch.attacker.example/watch'), false);
});

test('frontend reel/share detection uses parsed hostname and path', () => {
  assert.equal(isFacebookReelOrShareUrl('https://WWW.FACEBOOK.COM./share/r/example/?x=1'), true);
  assert.equal(isFacebookReelOrShareUrl('https://facebook.com.attacker.example/share/r/example/'), false);
  assert.equal(isFacebookReelOrShareUrl('https://attackerfacebook.com/reel/123'), false);
});

test('frontend hostname helpers reject malformed urls', () => {
  assert.equal(parseHostname('not-a-url'), '');
  assert.equal(isSocialShareUrl('not-a-url'), false);
  assert.equal(isFacebookReelOrShareUrl('facebook.com/reel/123'), false);
});
