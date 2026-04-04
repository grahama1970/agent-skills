/**
 * Sanity check: verify pdfjs-dist imports and getDocument exists.
 */
import * as pdfjsLib from 'pdfjs-dist';

const { getDocument, GlobalWorkerOptions } = pdfjsLib;

if (typeof getDocument !== 'function') {
  throw new Error('pdfjs-dist: getDocument is not a function');
}

if (typeof GlobalWorkerOptions !== 'object' || GlobalWorkerOptions === null) {
  throw new Error('pdfjs-dist: GlobalWorkerOptions is not an object');
}

console.log('pdfjs-dist OK — getDocument:', typeof getDocument);
console.log('pdfjs-dist version:', pdfjsLib.version ?? '(version not exposed)');
