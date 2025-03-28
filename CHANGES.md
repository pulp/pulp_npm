# Changelog

[//]: # (You should *NOT* be adding new change log entries to this file, this)
[//]: # (file is managed by towncrier. You *may* edit previous change logs to)
[//]: # (fix problems like typo corrections or such.)
[//]: # (To add a new change log entry, please see the contributing docs.)
[//]: # (WARNING: Don't drop the towncrier directive!)

[//]: # (towncrier release notes start)

## 0.3.2 (2025-03-28) {: #0.3.2 }

#### Misc {: #0.3.2-misc }

- 

---

## 0.3.1 (2025-03-27) {: #0.3.1 }

No significant changes.

---

## 0.3.0 (2025-03-21) {: #0.3.0 }

#### Features {: #0.3.0-feature }

- Enabled adding pulp-through content to a associated repository.
  [#299](https://github.com/pulp/pulp_npm/issues/299)

#### Improved Documentation {: #0.3.0-doc }

- Fixes the domain usage examples in the docs.
  [#298](https://github.com/pulp/pulp_npm/issues/298)

---

## 0.2.0 (2025-02-20) {: #0.2.0 }

#### Features {: #0.2.0-feature }

- Added pull-through cache feature.
  [#278](https://github.com/pulp/pulp_npm/issues/278)

#### Misc {: #0.2.0-misc }

- [#128](https://github.com/pulp/pulp_npm/issues/128)

---

### Bugfixes

-   Remove scheme from apache snippet
    [#8574](https://pulp.plan.io/issues/8574)
-   Adjusted the use of `dispatch` for pulpcore>=3.15. Also bumped the dependency.
    [#9533](https://pulp.plan.io/issues/9533)

---

## 0.1.0 (2025-02-14) {: #0.1.0 }

#### Features {: #0.1.0-feature }

- Bumped pulpcore compatibility to >=3.25.0,<3.40.
  [#229](https://github.com/pulp/pulp_npm/issues/229)
- Added Domains compatibility.
  [#273](https://github.com/pulp/pulp_npm/issues/273)

#### Bugfixes {: #0.1.0-bugfix }

- Fixes a sync operation demanding the remote URL when the repository already have one.
  [#275](https://github.com/pulp/pulp_npm/issues/275)
- Fixes the missing REMOTE_TYPES property of the NpmRepository class.
  [#276](https://github.com/pulp/pulp_npm/issues/276)

#### Misc {: #0.1.0-misc }

- [#268](https://github.com/pulp/pulp_npm/issues/268)

---

## 0.1.0a4 (2022-06-27)

### Bugfixes

-   Remove scheme from apache snippet
    [#8574](https://pulp.plan.io/issues/8574)
-   Adjusted the use of `dispatch` for pulpcore>=3.15. Also bumped the dependency.
    [#9533](https://pulp.plan.io/issues/9533)

---

## 0.1.0a3 (2021-03-17)

No significant changes.

---

## 0.1.0a2 (2020-11-25)

No significant changes.

---

## 0.1.0a1 (2020-11-18)

### Features

-   Download a package with its dependencies
    [#6004](https://pulp.plan.io/issues/6004)
