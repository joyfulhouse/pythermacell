# CI/CD Pipeline Documentation

**Last Updated**: 2025-11-19

This document describes the Continuous Integration and Continuous Deployment (CI/CD) pipeline for the pythermacell project.

## Table of Contents

- [Overview](#overview)
- [Workflows](#workflows)
- [Environments](#environments)
- [Branch Protection](#branch-protection)
- [Publishing Process](#publishing-process)
- [Secrets Management](#secrets-management)

## Overview

The pythermacell project uses GitHub Actions for CI/CD with two separate workflows:

1. **CI Pipeline** (`ci.yml`) - Runs on every PR and push to main
2. **Publish Pipeline** (`publish.yml`) - Runs on GitHub releases

### Pipeline Philosophy

- **Fast feedback**: Linting and unit tests run on every commit
- **Safe merges**: Integration tests required before merging to main
- **Controlled releases**: Publishing requires manual GitHub release creation
- **Quality gates**: All checks must pass before deployment

## Workflows

### 1. CI Pipeline (`.github/workflows/ci.yml`)

**Triggers**:
- Pull requests to `main`
- Pushes to `main`
- Manual workflow dispatch

**Jobs**:

#### Lint Job
Runs code quality checks:
- Ruff linting (`ruff check`)
- Ruff formatting (`ruff format --check`)
- Mypy type checking (`mypy --strict`)

**Requirements**: Python 3.13

#### Test Job
Runs unit tests:
- Tests on Python 3.13 and 3.14
- Coverage reporting to Codecov
- Minimum 90% coverage target

**Requirements**:
- Python 3.13, 3.14
- >90% test coverage

#### Integration Test Job
Runs integration tests against real Thermacell API:
- Requires manual approval (environment protection)
- Uses GitHub Secrets for credentials
- Only runs on PRs to main and main branch pushes

**Requirements**:
- Python 3.13
- GitHub Secrets configured
- Environment: `integration-tests`
- Manual approval required

### 2. Publish Pipeline (`.github/workflows/publish.yml`)

**Triggers**:
- GitHub Release published
- Manual workflow dispatch (with environment selection)

**Jobs**:

#### Lint, Test, Integration Test
Same as CI pipeline - ensures release quality

#### Publish to TestPyPI
- Builds Python package
- Publishes to https://test.pypi.org/
- Uses OIDC for authentication (no API tokens needed)

**Requirements**:
- All tests pass
- Environment: `testpypi`

#### Publish to PyPI
- Builds Python package
- Publishes to https://pypi.org/
- Uses OIDC for authentication
- Requires manual approval

**Requirements**:
- TestPyPI publish successful
- Environment: `pypi`
- Manual approval required

## Environments

### integration-tests

**Protection Rules**:
- ✅ Required reviewers: 1
- ✅ Wait timer: None
- ✅ Deployment branches: All branches

**Secrets**:
- `THERMACELL_USERNAME` - Thermacell account email
- `THERMACELL_PASSWORD` - Thermacell account password
- `THERMACELL_API_BASE_URL` - API base URL (https://api.iot.thermacell.com)
- `THERMACELL_TEST_NODE_ID` - Optional specific device ID

**Purpose**: Prevents integration tests from running automatically, requiring manual approval to test against real hardware/API.

### testpypi

**Protection Rules**:
- ❌ No required reviewers (automatic)
- ❌ No wait timer
- ✅ Deployment branches: All branches

**Secrets**: None (uses OIDC)

**Purpose**: Automatic test publishing to verify package builds correctly before PyPI release.

**OIDC Configuration**:
1. Go to https://test.pypi.org/manage/account/publishing/
2. Add publisher: `joyfulhouse/pythermacell`
3. Workflow: `publish.yml`
4. Environment: `testpypi`

### pypi

**Protection Rules**:
- ✅ Required reviewers: 1
- ✅ Wait timer: None
- ✅ Deployment branches: `main` only

**Secrets**: None (uses OIDC)

**Purpose**: Production PyPI releases require manual approval as final safety check.

**OIDC Configuration**:
1. Go to https://pypi.org/manage/account/publishing/
2. Add publisher: `joyfulhouse/pythermacell`
3. Workflow: `publish.yml`
4. Environment: `pypi`

## Branch Protection

### Main Branch Protection Rules

Configure at: https://github.com/joyfulhouse/pythermacell/settings/branch_protection_rules

**Required Status Checks**:
- ✅ `lint` - Linting & Type Checking
- ✅ `test (3.13)` - Unit Tests (Python 3.13)
- ✅ `test (3.14)` - Unit Tests (Python 3.14)
- ✅ `integration-test` - Integration Tests

**Branch Rules**:
- ✅ Require status checks to pass before merging
- ✅ Require branches to be up to date before merging
- ✅ Require linear history (no merge commits)
- ✅ Require signed commits (recommended)
- ❌ Allow force pushes: Disabled
- ❌ Allow deletions: Disabled

**Merge Options**:
- ✅ Allow squash merging
- ❌ Allow merge commits
- ❌ Allow rebase merging

### Setting Up Branch Protection

```bash
# Using GitHub CLI
gh api repos/joyfulhouse/pythermacell/branches/main/protection \
  --method PUT \
  --field required_status_checks[strict]=true \
  --field required_status_checks[contexts][]=lint \
  --field required_status_checks[contexts][]="test (3.13)" \
  --field required_status_checks[contexts][]="test (3.14)" \
  --field required_status_checks[contexts][]=integration-test \
  --field enforce_admins=true \
  --field required_pull_request_reviews[required_approving_review_count]=1 \
  --field restrictions=null
```

Or manually via GitHub UI:
1. Go to Settings → Branches
2. Click "Add branch protection rule"
3. Branch name pattern: `main`
4. Enable settings as listed above

## Publishing Process

### 1. Prepare Release

```bash
# Update version
# Edit pyproject.toml and src/pythermacell/__init__.py
__version__ = "0.2.0"

# Update CHANGELOG
# Edit docs/CHANGELOG.md

# Commit changes
git add pyproject.toml src/pythermacell/__init__.py docs/CHANGELOG.md
git commit -m "chore: Bump version to 0.2.0"
git push origin main
```

### 2. Create GitHub Release

1. Go to https://github.com/joyfulhouse/pythermacell/releases
2. Click "Draft a new release"
3. Click "Choose a tag"
4. Type new tag: `v0.2.0` (must start with `v`)
5. Click "Create new tag: v0.2.0 on publish"
6. Release title: `v0.2.0`
7. Description: Copy from CHANGELOG.md
8. Click "Publish release"

### 3. Automated Publishing

The publish workflow will automatically:

1. **Lint & Test**
   - Run all quality checks
   - Run unit tests on Python 3.13 and 3.14

2. **Integration Tests**
   - Wait for manual approval
   - Run integration tests against real API

3. **TestPyPI**
   - Build package
   - Publish to https://test.pypi.org/project/pythermacell/
   - Verify installation works

4. **PyPI**
   - Wait for manual approval
   - Build package
   - Publish to https://pypi.org/project/pythermacell/

### 4. Verify Release

```bash
# Test installation from TestPyPI
pip install --index-url https://test.pypi.org/simple/ pythermacell==0.2.0

# Test installation from PyPI (after approval)
pip install pythermacell==0.2.0
```

## Secrets Management

### Repository Secrets

Stored at: https://github.com/joyfulhouse/pythermacell/settings/secrets/actions

#### Current Secrets

| Secret | Environment | Description | Set Via |
|--------|-------------|-------------|---------|
| `THERMACELL_USERNAME` | integration-tests | Thermacell account email | GitHub CLI |
| `THERMACELL_PASSWORD` | integration-tests | Thermacell account password | GitHub CLI |
| `THERMACELL_API_BASE_URL` | integration-tests | API base URL | GitHub CLI |
| `THERMACELL_TEST_NODE_ID` | integration-tests | Optional device ID | GitHub CLI |

#### Adding/Updating Secrets

Using GitHub CLI:

```bash
# Set secret
gh secret set THERMACELL_USERNAME \
  --body "your@email.com" \
  --repo joyfulhouse/pythermacell

# List secrets
gh secret list --repo joyfulhouse/pythermacell

# Delete secret
gh secret delete THERMACELL_USERNAME --repo joyfulhouse/pythermacell
```

Using GitHub UI:
1. Go to Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Name: `THERMACELL_USERNAME`
4. Value: `your@email.com`
5. Click "Add secret"

### Security Best Practices

1. **Never commit secrets** - Always use GitHub Secrets
2. **Rotate credentials** - Change passwords regularly
3. **Limit scope** - Use test account for integration tests
4. **Audit access** - Review secret access logs periodically
5. **Use OIDC** - PyPI publishing uses OIDC (no API tokens)

## Troubleshooting

### Integration Tests Failing

**Problem**: Integration tests fail with authentication error

**Solution**:
1. Verify secrets are set correctly
2. Check credentials work in browser
3. Ensure device is online and accessible
4. Check API rate limits

### PyPI Publishing Fails

**Problem**: OIDC authentication fails

**Solution**:
1. Verify OIDC publisher is configured on PyPI/TestPyPI
2. Ensure workflow name and environment name match exactly
3. Check environment protection rules allow deployment
4. Verify repository has OIDC write permissions

### Coverage Drops Below 90%

**Problem**: New code reduces coverage

**Solution**:
1. Add tests for new functionality
2. Use `pytest --cov-report=html` to identify gaps
3. Run `pytest --cov-report=term-missing` to see missing lines
4. Don't skip tests - improve coverage

### Branch Protection Prevents Merge

**Problem**: PR cannot merge despite passing tests

**Solution**:
1. Ensure all required checks are passing
2. Branch must be up-to-date with main
3. Integration test approval required
4. Check for merge conflicts

## Monitoring

### CI/CD Metrics

Monitor these metrics:
- ✅ **Success rate**: % of successful pipeline runs
- ⏱️ **Build time**: Time from commit to deploy
- 🐛 **Failure rate**: % of failed builds
- 📦 **Release frequency**: Releases per month

### Alerts

Set up alerts for:
- Integration test failures
- PyPI publishing failures
- Coverage drops
- Security vulnerabilities

## Future Improvements

Planned enhancements:
- [ ] Codecov integration for PR comments
- [ ] Automatic changelog generation
- [ ] Performance benchmarks in CI
- [ ] Security scanning (Dependabot, CodeQL)
- [ ] Docker image publishing
- [ ] Documentation deployment to GitHub Pages

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [PyPI Publishing with OIDC](https://docs.pypi.org/trusted-publishers/)
- [Branch Protection Rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [Codecov Documentation](https://docs.codecov.com/)

---

**Need help?** Open an issue or discussion at https://github.com/joyfulhouse/pythermacell
