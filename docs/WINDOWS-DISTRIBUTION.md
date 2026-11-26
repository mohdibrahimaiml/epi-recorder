# Windows distribution

Who gets what:

| Audience | Channel | Signed by |
|---|---|---|
| Developers adding EPI to their code | `pip install epi-recorder` (PyPI) | PEP 740 build attestations |
| Reviewers who open `.epi` files, no install | <https://epilabs.org/verify> in the browser | nothing to install |
| Reviewers who want a Windows app | Microsoft Store | Microsoft, free |
| Anyone downloading the installer directly | `epi-setup-<version>.exe` on GitHub Releases | SignPath Foundation, free for open source (once approved) |

The installer needs admin rights (it registers the `.epi` file type for all
users). The Store package does not, which suits locked-down work laptops.

## Microsoft Store

Workflow: `.github/workflows/build-msix.yml`. Manifest:
`installer/msix/AppxManifest.xml`. Script: `scripts/build_msix.ps1`.

1. **Register** at Partner Center as a developer (free for individuals since
   September 2025 and for companies since May 2026; confirm on the sign-up
   page).
2. **Reserve the app name** "EPI Recorder" (or your chosen name).
3. In the app's **Product identity** page, copy three values into repository
   variables (Settings > Secrets and variables > Actions > Variables):
   - `MSIX_IDENTITY_NAME` = Package/Identity/Name
   - `MSIX_PUBLISHER` = Package/Identity/Publisher (starts with `CN=`)
   - `MSIX_PUBLISHER_DISPLAY_NAME` = Package/Properties/PublisherDisplayName
4. **Run** Actions > Build MSIX (Microsoft Store) with the release tag (e.g.
   `v4.11.2`). Download the `epi-msix` artifact.
5. **Submit** the `.msix` in Partner Center. Declare the `runFullTrust`
   capability as required for a desktop command-line tool. Microsoft signs the
   package on publication.

Without the three variables the workflow builds with a test identity
(`CN=EPI Labs Test`). That build is installed on the runner, test-signed, to
check that it installs, that `epi --version` works and that a sample `.epi`
verifies. This check is required: the job fails if it does not pass. The Store
rejects the test identity, by design. Not covered by CI: double-clicking a
`.epi` file in Explorer.

What the package provides:
- Start menu entry **EPI Recorder**, which opens the viewer (`epi view`).
- The `epi` command in any terminal (app execution alias).
- Double-clicking a `.epi` file runs `epi view "<file>"`.

## SignPath Foundation (installer on GitHub Releases)

Workflow: `.github/workflows/build-windows-installer.yml`. Policy:
`CODE_SIGNING_POLICY.md` (linked from the README; SignPath requires it).

1. **Apply** at <https://signpath.org> for the `epi-recorder` repository.
2. After approval, in SignPath create a project with:
   - an artifact configuration that signs the setup exe inside the zip GitHub
     uploads, for example:
     ```xml
     <artifact-configuration xmlns="http://signpath.io/artifact-configuration/v1">
       <zip-file>
         <pe-file path="epi-setup-*.exe">
           <authenticode-sign />
         </pe-file>
       </zip-file>
     </artifact-configuration>
     ```
   - a release signing policy linked to this repository's GitHub Actions.
3. Set repository **variables** `SIGNPATH_ORGANIZATION_ID`,
   `SIGNPATH_PROJECT_SLUG`, `SIGNPATH_SIGNING_POLICY_SLUG` and the repository
   **secret** `SIGNPATH_API_TOKEN`.
4. The next tagged release signs the installer before SHA256SUMS and Sigstore
   run. The workflow refuses to publish if the returned file's Authenticode
   signature is not valid.

Until step 3 is done, the installer is built and published unsigned, exactly as
before.

Not yet covered: `epi.exe` inside the installer is not signed separately. A
second signing request before the Inno Setup step would cover it.
