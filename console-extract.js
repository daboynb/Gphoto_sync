// Google Photos Locale Extractor
//
// COSA ESTRAE:
// - METADATA_FORMAT: Formato esatto dei metadati foto (es. "13 nov 2025, 14:32:41")
// - MONTHS: 12 mesi abbreviati nella lingua usata da Google Photos
// - DATE_FORMAT: Tipo di formato rilevato (italiano/inglese/tedesco)
// - DETECTED_LOCALE: Locale utilizzato (es. it-IT, en-US, de-DE)
//
// COME FUNZIONA:
// 1. Estrae il metadata format da una foto aperta
// 2. Analizza il formato della data (giorno-mese vs mese-giorno, presenza punti, ecc.)
// 3. Rileva il locale dalla struttura e dalla lingua della pagina (document.documentElement.lang)
// 4. Genera i 12 mesi usando toLocaleDateString() con il locale rilevato
//    (stessa API usata da Google Photos - i mesi NON sono hardcoded negli script!)
//

(async function() {
  const pageLang = document.documentElement.lang;
  const browserLocale = navigator.language || 'en-US';

  // Extract metadata
  let metadataFormat = null;
  let labels = [...document.querySelectorAll('[aria-label]')]
    .map(e => e.getAttribute('aria-label'))
    .filter(l => l && l.includes(' - '));

  if (labels.length === 0) {
    const infoBtn = [...document.querySelectorAll('button[aria-label]')].find(b => {
      const label = b.getAttribute('aria-label')?.toLowerCase() || '';
      return label.includes('info') || label.includes('informazioni');
    });
    if (infoBtn) {
      infoBtn.click();
      await new Promise(r => setTimeout(r, 2000));
      labels = [...document.querySelectorAll('[aria-label]')]
        .map(e => e.getAttribute('aria-label'))
        .filter(l => l && l.includes(' - '));
    }
  }

  if (labels.length > 0) metadataFormat = labels[0];

  // Detect format and generate months
  let months = [];
  let detectedLocale = null;
  let dateFormat = 'unknown';

  if (metadataFormat) {
    const germanMatch = metadataFormat.match(/(\d{1,2})\.\s+(\w+)\.\s+(\d{4}),/);
    const englishMatch = metadataFormat.match(/(\w+)\s+(\d{1,2}),\s+(\d{4}),/);
    const europeanMatch = metadataFormat.match(/(\d{1,2})\s+(\w+)\s+(\d{4}),/);

    if (germanMatch) {
      dateFormat = 'de (day. month. year)';
      detectedLocale = 'de-DE';
    } else if (englishMatch) {
      dateFormat = 'en (month day, year)';
      detectedLocale = 'en-US';
    } else if (europeanMatch) {
      dateFormat = 'eu (day month year)';
      detectedLocale = pageLang || 'it-IT';
    }

    if (detectedLocale) {
      for (let i = 0; i < 12; i++) {
        const date = new Date(2024, i, 1);
        months.push(date.toLocaleDateString(detectedLocale, { month: 'short' }).replace(/\./g, ''));
      }
    }
  }

  // Output
  console.log('METADATA_FORMAT:');
  console.log(metadataFormat || 'Not found');
  console.log('');
  console.log('MONTHS:');
  console.log(months.join(', ') || 'Not found');
  console.log('');
  console.log('DATE_FORMAT: ' + dateFormat);
  console.log('DETECTED_LOCALE: ' + (detectedLocale || 'unknown'));
  console.log('PAGE_LANG: ' + pageLang);
  console.log('BROWSER_LOCALE: ' + browserLocale);
})();
