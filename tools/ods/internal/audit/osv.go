package audit

import (
	"errors"
	"log/slog"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"

	"github.com/google/osv-scanner/v2/pkg/models"
	"github.com/google/osv-scanner/v2/pkg/osvscanner"
	"github.com/ossf/osv-schema/bindings/go/osvschema"
)

// ponytail: the SDK has a global logger; serialize scans until it supports per-scan loggers.
var sdkScanMutex sync.Mutex

func scanOSV(actions osvscanner.ScannerActions, scan func(osvscanner.ScannerActions) (models.VulnerabilityResults, error)) (models.VulnerabilityResults, error) {
	sdkScanMutex.Lock()
	defer sdkScanMutex.Unlock()
	var loggedError atomic.Bool
	osvscanner.SetLogger(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{
		Level: slog.LevelWarn,
		ReplaceAttr: func(_ []string, attribute slog.Attr) slog.Attr {
			if level, ok := attribute.Value.Any().(slog.Level); attribute.Key == slog.LevelKey && ok && level >= slog.LevelError {
				loggedError.Store(true)
			}
			return attribute
		},
	}))
	result, err := scan(actions)
	if errors.Is(err, osvscanner.ErrVulnerabilitiesFound) || errors.Is(err, osvscanner.ErrNoPackagesFound) {
		err = nil
	}
	if err == nil && loggedError.Load() {
		return models.VulnerabilityResults{}, errors.New("OSV logged scan errors; refusing incomplete results")
	}
	return result, err
}

// osvBaseURL is the canonical OSV.dev vulnerability page prefix.
const osvBaseURL = "https://osv.dev/vulnerability/"

// scanLockfiles runs osv-scanner (as a library) over the given lockfiles and
// maps the results into Findings. Returns nil when there are no lockfiles.
func scanLockfiles(lockfiles []string) ([]Finding, error) {
	if len(lockfiles) == 0 {
		return nil, nil
	}
	res, err := scanOSV(osvscanner.ScannerActions{LockfilePaths: lockfiles}, osvscanner.DoScan)
	if err != nil {
		return nil, err
	}
	return findingsFromResults(res), nil
}

// findingsFromResults maps osv-scanner's VulnerabilityResults into Findings.
// It is pure (no I/O) so it can be unit tested against fixtures.
func findingsFromResults(res models.VulnerabilityResults) []Finding {
	var findings []Finding
	for _, src := range res.Results {
		for _, pkg := range src.Packages {
			for _, group := range pkg.Groups {
				f := findingFromGroup(group, pkg)
				f.Manifest = src.Source.Path
				findings = append(findings, f)
			}
		}
	}
	return findings
}

func findingFromGroup(group models.GroupInfo, pkg models.PackageVulns) Finding {
	id := representativeID(group.IDs)
	f := Finding{
		ID:        id,
		Aliases:   group.Aliases,
		Ecosystem: pkg.Package.Ecosystem,
		Package:   pkg.Package.Name,
		Version:   pkg.Package.Version,
		Severity:  severityForGroup(group, pkg),
		URL:       osvBaseURL + id,
		Source:    SourceOSV,
	}
	if vuln := findVuln(pkg.Vulnerabilities, group.IDs); vuln != nil {
		f.Title = vulnTitle(vuln)
	}
	return f
}

// vulnTitle returns a one-line title for an advisory, preferring the summary
// and falling back to the first line of the details.
func vulnTitle(vuln *osvschema.Vulnerability) string {
	if summary := strings.TrimSpace(vuln.GetSummary()); summary != "" {
		return summary
	}
	details := strings.TrimSpace(vuln.GetDetails())
	if details == "" {
		return ""
	}
	if line, _, found := strings.Cut(details, "\n"); found {
		return strings.TrimSpace(line)
	}
	return details
}

// severityForGroup derives a Severity, preferring the CVSS-based MaxSeverity
// osv-scanner computes for the group, and falling back to the GHSA-style
// database_specific.severity label when no CVSS vector is available.
func severityForGroup(group models.GroupInfo, pkg models.PackageVulns) Severity {
	if group.MaxSeverity != "" {
		if score, err := strconv.ParseFloat(group.MaxSeverity, 64); err == nil {
			if sev := SeverityFromCVSS(score); sev != SeverityUnknown {
				return sev
			}
		}
	}
	if vuln := findVuln(pkg.Vulnerabilities, group.IDs); vuln != nil {
		if label := databaseSpecificSeverity(vuln); label != "" {
			return ParseSeverity(label)
		}
	}
	return SeverityUnknown
}

// databaseSpecificSeverity extracts a "severity" string (e.g. "CRITICAL") from
// the advisory's database_specific block, when present.
func databaseSpecificSeverity(vuln *osvschema.Vulnerability) string {
	ds := vuln.GetDatabaseSpecific()
	if ds == nil {
		return ""
	}
	if v, ok := ds.AsMap()["severity"].(string); ok {
		return v
	}
	return ""
}

// representativeID picks a stable display id for a group of aliased advisories.
func representativeID(ids []string) string {
	if len(ids) == 0 {
		return ""
	}
	return ids[0]
}

// findVuln returns the first vulnerability record whose id is in ids.
func findVuln(vulns []*osvschema.Vulnerability, ids []string) *osvschema.Vulnerability {
	idset := make(map[string]bool, len(ids))
	for _, id := range ids {
		idset[id] = true
	}
	for _, v := range vulns {
		if idset[v.GetId()] {
			return v
		}
	}
	return nil
}

func fileExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}
