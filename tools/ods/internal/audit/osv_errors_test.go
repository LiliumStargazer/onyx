package audit

import (
	"context"
	"testing"

	scalibrlog "github.com/google/osv-scalibr/log"
	"github.com/google/osv-scanner/v2/pkg/models"
	"github.com/google/osv-scanner/v2/pkg/osvscanner"
)

func TestScanOSVRejectsLoggedErrorsWithPartialResults(t *testing.T) {
	for _, partialError := range []bool{false, true} {
		t.Run(map[bool]string{false: "complete", true: "partial timeout"}[partialError], func(t *testing.T) {
			result, err := scanOSV(osvscanner.ScannerActions{}, func(osvscanner.ScannerActions) (models.VulnerabilityResults, error) {
				if partialError {
					scalibrlog.Errorf("error when retrieving vulns: %v", context.DeadlineExceeded)
				}
				return models.VulnerabilityResults{Results: []models.PackageSource{{}}}, osvscanner.ErrVulnerabilitiesFound
			})
			if partialError {
				if err == nil || result.Results != nil {
					t.Fatalf("expected rejection of partial results, got %+v, %v", result, err)
				}
			} else if err != nil || len(result.Results) != 1 {
				t.Fatalf("expected complete results, got %+v, %v", result, err)
			}
		})
	}
}
