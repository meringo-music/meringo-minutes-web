# Vendored code

Third-party files served by this site, copied byte for byte from their
published packages. Nothing here is edited; to update one, replace the file
and its hash in the same commit.

| File | From | SHA-256 |
|---|---|---|
| `minisearch-7.1.2.js` | npm `minisearch@7.1.2`, `package/dist/es/index.js` | `e87dfe790d3d11106d658ff6cef8f5561d1a6f4145d8645af6f909bdf1eb29f0` |
| `minisearch-LICENSE.txt` | npm `minisearch@7.1.2`, `package/LICENSE.txt` (MIT, © 2022 Luca Ongaro) | `70d37354d6395629fb99edb28cb37a5d356ffa24a48cd02a5def5b83a300a899` |

The package tarball was fetched with `npm pack minisearch@7.1.2`; its SHA-1,
`296ee8d1906cc378f7e57a3a71f07e5205a75df5`, matches the registry's
`dist.shasum`. To check the file yourself:

```
npm pack minisearch@7.1.2
tar xzf minisearch-7.1.2.tgz package/dist/es/index.js
sha256sum package/dist/es/index.js
```

MiniSearch is loaded only on /faq/, by `assets/js/ask-ui.js`, from this
origin. It builds the question index in the browser; nothing is sent anywhere.
The file's last line names a source map that isn't vendored, so a browser's
developer tools may note a missing `index.js.map`; the page doesn't request it.

`.gitattributes` marks this folder `-text`, so a Windows checkout can't change
the line endings and the hash.
