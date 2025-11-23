package utils

import (
	"net/url"
)

// AbsInt returns the absolute value of an integer
func AbsInt(x int) int {
	if x < 0 {
		return -x
	}
	return x
}

// CompareMangled compares two file names, where s2 is sometimes mangled by gphotos
// there will be some false positives, this is ok
func CompareMangled(_s1, _s2 string) bool {
	doCompare := func(s1, s2 string) bool {
		sr1 := []rune(s1)
		sr2 := []rune(s2)

		l1 := len(sr1)
		for i := len(sr1) - 1; i >= 0; i-- {
			if sr1[i] == '.' {
				l1 = i + 1
				break
			}
		}

		l2 := len(sr2)
		for i := len(sr2) - 1; i >= 0; i-- {
			if sr2[i] == '.' {
				l2 = i + 1
				break
			}
		}

		i1 := 0
		for i1 < len(sr1) && sr1[i1] == '.' && sr2[i1] != '.' {
			i1++
		}

		for i2 := 0; i2 < l2; i2++ {
			if i1 >= len(sr1) {
				return i2 == l2-1 && sr2[i2] == '.'
			}
			if sr1[i1] != sr2[i2] && sr2[i2] != '_' {
				return false
			}
			i1++
		}

		return i1 >= l1
	}

	if doCompare(_s1, _s2) {
		return true
	}

	// URL-decoding s1 since Google Photos may return URL-encoded filenames
	if decoded, err := url.QueryUnescape(_s1); err == nil {
		return doCompare(decoded, _s2)
	}

	return false
}
