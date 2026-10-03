package audit

import (
	"reflect"
	"testing"
)

func TestScanActionsKeepsOnlySelectedWorkflowsBeforeDeduplication(t *testing.T) {
	root := chdirNewRepo(t)
	workflow := "jobs:\n  build:\n    steps:\n      - uses: tj-actions/changed-files@v45.0.7\n"
	writeFixture(t, root, ".github/workflows/deployment.yml", workflow)
	writeFixture(t, root, ".github/workflows/release.yml", workflow)
	_, url := startFakeOSV(t, map[string][]osvVuln{"tj-actions/changed-files": {changedFilesAdvisory()}})

	findings, err := scanActions(url, ".github/workflows/release.yml")
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 1 || findings[0].Manifest != ".github/workflows/release.yml" {
		t.Fatalf("expected the selected workflow finding, got %+v", findings)
	}
	if _, err := scanActions(url, ".github/workflows/missing.yml"); err == nil {
		t.Fatal("expected an error for a missing selected workflow")
	}
}

func TestLockfilePathsIncludesExplicitGoModule(t *testing.T) {
	root := chdirNewRepo(t)
	writeFixture(t, root, "tools/ods/go.mod", "module example.com/audit\n")
	files, err := lockfilePaths(false, false, "tools/ods/go.mod")
	if err != nil {
		t.Fatal(err)
	}
	want := []string{root + "/tools/ods/go.mod"}
	if !reflect.DeepEqual(files, want) {
		t.Fatalf("expected %v, got %v", want, files)
	}
	if _, err := lockfilePaths(false, false, "missing/go.mod"); err == nil {
		t.Fatal("expected an error for a missing explicit manifest")
	}
}
