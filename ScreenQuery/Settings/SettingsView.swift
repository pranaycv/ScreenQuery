import SwiftUI

struct SettingsView: View {
    @ObservedObject var settings: SettingsStore
    @ObservedObject var permissions: PermissionCenter
    var onRecheck: () -> Void

    @State private var apiKeyDraft = ""
    @State private var keyStatus = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                header
                actionsSection
                folderSection
                modelSection
                overlaySection
                permissionsSection
            }
            .padding(24)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(minWidth: 560, minHeight: 520)
        .onAppear(perform: refreshKeyStatus)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("ScreenQuery")
                .font(.title2.weight(.semibold))
            Text("Press Shift+S+P anywhere to capture the screen. Save a PNG, ask a vision model, or both.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var actionsSection: some View {
        section("Actions", subtitle: "Either action can be on by itself. If both are off, the hotkey only shows a reminder.") {
            Toggle("Save screenshot", isOn: $settings.saveEnabled)
            Toggle("Send to LLM", isOn: $settings.llmEnabled)
            if !settings.saveEnabled && !settings.llmEnabled {
                Text("Turn on at least one action.")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
        }
    }

    private var folderSection: some View {
        section("Save location", subtitle: "The default folder is ~/ScreenQuery/ with a subfolder for today's date. A chosen folder is used as-is. Filenames are timestamped.") {
            Picker("Folder", selection: $settings.useCustomFolder) {
                Text("Default (~/ScreenQuery/date)").tag(false)
                Text("Chosen folder").tag(true)
            }
            .pickerStyle(.radioGroup)
            .labelsHidden()

            Text(settings.folderDescription)
                .font(.system(.body, design: .monospaced))
                .foregroundStyle(.secondary)
                .lineLimit(2)
                .truncationMode(.middle)
                .textSelection(.enabled)

            HStack {
                Button("Choose Folder…") { settings.chooseFolder() }
                Button("Show in Finder") { settings.revealSaveFolder() }
            }
        }
    }

    private var modelSection: some View {
        section("Language model", subtitle: "OpenAI-compatible vision endpoint. The API key is stored in the Keychain and is not written to preferences. The screenshot is sent only to the URL you enter.") {
            LabeledContent("Base URL") {
                TextField("https://api.openai.com/v1", text: $settings.llmBaseURL)
                    .textFieldStyle(.roundedBorder)
            }
            LabeledContent("Model") {
                TextField("gpt-4o", text: $settings.llmModel)
                    .textFieldStyle(.roundedBorder)
            }
            Text("The model must accept image input. gpt-4o is a working default. Point the base URL at any compatible server, including a local one.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            LabeledContent("API key") {
                SecureField("Paste API key", text: $apiKeyDraft)
                    .textFieldStyle(.roundedBorder)
            }
            HStack {
                Button("Save to Keychain") { saveKey() }
                    .disabled(apiKeyDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                Button("Remove Key") { removeKey() }
                Text(keyStatus)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text("Prompt")
                .font(.subheadline.weight(.medium))
            TextField("Instruction sent with the screenshot", text: $settings.llmPrompt, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(3...6)
        }
    }

    private var overlaySection: some View {
        section("Status overlay", subtitle: "After a capture, a floating window reports the saved path and the model response. It stays up while the pointer is over it.") {
            Stepper(value: $settings.overlayDismissSeconds, in: 4...120) {
                Text("Dismiss after \(settings.overlayDismissSeconds) seconds")
            }
        }
    }

    private var permissionsSection: some View {
        section("Permissions", subtitle: "macOS ties each grant to this copy of the app. After toggling a permission, quit and reopen ScreenQuery if the hotkey or capture still fails. A new build or a copy in /Applications is a different identity — remove the old entry and enable it again.") {
            permissionRow(
                title: "Screen Recording",
                detail: "Required to capture the display.",
                granted: permissions.screenRecording,
                grant: { permissions.requestScreenRecording() },
                open: { PermissionCenter.openScreenRecordingSettings() }
            )
            permissionRow(
                title: "Accessibility",
                detail: "Required on some macOS versions to observe global key events.",
                granted: permissions.accessibility,
                grant: { permissions.requestAccessibility() },
                open: { PermissionCenter.openAccessibilitySettings() }
            )
            permissionRow(
                title: "Input Monitoring",
                detail: "Required to see the Shift+S+P chord while another app is focused.",
                granted: permissions.inputMonitoring,
                grant: { permissions.requestInputMonitoring() },
                open: { PermissionCenter.openInputMonitoringSettings() }
            )
            HStack(spacing: 8) {
                Image(systemName: permissions.hotkeyTapInstalled ? "checkmark.circle.fill" : "exclamationmark.circle.fill")
                    .foregroundStyle(permissions.hotkeyTapInstalled ? Color.green : Color.orange)
                Text(permissions.hotkeyTapInstalled ? "Hotkey monitor is running." : "Hotkey monitor is not running.")
                    .font(.callout)
                Spacer()
                Button("Recheck", action: onRecheck)
            }
        }
    }

    private func permissionRow(
        title: String,
        detail: String,
        granted: Bool,
        grant: @escaping () -> Void,
        open: @escaping () -> Void
    ) -> some View {
        HStack(alignment: .center, spacing: 10) {
            Image(systemName: granted ? "checkmark.circle.fill" : "xmark.circle.fill")
                .foregroundStyle(granted ? Color.green : Color.red)
                .imageScale(.large)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 8)
            Button("Grant", action: grant)
            Button("System Settings", action: open)
        }
    }

    private func section<Content: View>(_ title: String, subtitle: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.headline)
            Text(subtitle)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            content()
            Divider()
        }
    }

    private func refreshKeyStatus() {
        keyStatus = KeychainStore.containsAPIKey() ? "A key is saved in the Keychain." : "No key saved."
    }

    private func saveKey() {
        do {
            try KeychainStore.saveAPIKey(apiKeyDraft)
            apiKeyDraft = ""
            keyStatus = "Saved to the Keychain."
        } catch {
            keyStatus = error.localizedDescription
        }
    }

    private func removeKey() {
        KeychainStore.deleteAPIKey()
        apiKeyDraft = ""
        keyStatus = "Key removed."
    }
}
