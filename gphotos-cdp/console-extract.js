// Google Photos Locale Extractor

(function() {
  const pageLang = document.documentElement.lang;
  const browserLocale = navigator.language;

  // Extract metadata - simply get all aria-labels containing ' - '
  let metadataFormat = null;
  let labels = [...document.querySelectorAll('[aria-label]')]
    .map(e => e.getAttribute('aria-label'))
    .filter(l => l && l.includes(' - '));

  if (labels.length > 0) metadataFormat = labels[0];

  // Detect format and generate months
  let months = [];
  let dateFormat = 'unknown';

  if (metadataFormat) {
    // Detect date format pattern by structure only
    if (metadataFormat.match(/(\d{1,2})\.\s+(\w+)\.\s+(\d{4}),/)) {
      dateFormat = 'day. month. year';
    } else if (metadataFormat.match(/(\w+)\s+(\d{1,2}),\s+(\d{4}),/)) {
      dateFormat = 'month day, year';
    } else if (metadataFormat.match(/(\d{1,2})\s+(\w+)\s+(\d{4}),/)) {
      dateFormat = 'day month year';
    }

    // Generate months using page language
    if (pageLang && dateFormat !== 'unknown') {
      for (let i = 0; i < 12; i++) {
        const date = new Date(2024, i, 1);
        months.push(date.toLocaleDateString(pageLang, { month: 'short' }).replace(/\./g, ''));
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
  console.log('PAGE_LANG: ' + pageLang);
  console.log('BROWSER_LOCALE: ' + browserLocale);
})();
