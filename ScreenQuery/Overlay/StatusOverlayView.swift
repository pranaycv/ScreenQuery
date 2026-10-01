import SwiftUI

struct StatusOverlayView: View {
    @ObservedObject var model: OverlayModel
    var onDismiss: () -> Void
    var onReveal: () -> Void
    var onCopy: () -> Void
    var onAction: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            HStack(spacing: 8) {
                if model.showProgress {
                    ProgressView()
                        .controlSize(.small)
                        .tint(.white)
                }
                Text(model.llmPending ? "Asking the model…" : model.headline)
                    .font(.callout.weight(.semibold))
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let savedPath = model.savedPath {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(Color(red: 0.55, green: 0.90, blue: 0.75))
                    Text(savedPath)
                        .font(.system(.callout, design: .monospaced))
                        .lineLimit(3)
                        .truncationMode(.middle)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            if let note = model.note, !note.isEmpty {
                Text(note)
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.78))
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let llmText = model.llmText, !llmText.isEmpty {
                ScrollView {
                    Text(llmText)
                        .font(.system(size: 13))
                        .lineSpacing(3)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(height: responseHeight(for: llmText))
            }
            ForEach(Array(visibleErrors.enumerated()), id: \.offset) { _, error in
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(Color(red: 1.0, green: 0.74, blue: 0.48))
                    Text(error)
                        .font(.callout)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            footer
        }
        .padding(16)
        .frame(width: 400, alignment: .leading)
        .foregroundStyle(.white)
        .background {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(.ultraThinMaterial)
                .overlay {
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .fill(Color.black.opacity(0.48))
                }
        }
        .overlay {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(Color.white.opacity(0.16), lineWidth: 1)
        }
        .contentShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .onTapGesture(perform: onDismiss)
        .padding(14)
        .preferredColorScheme(.dark)
    }

    private var visibleErrors: [String] {
        model.errors.filter { $0 != model.headline }
    }

    private func responseHeight(for text: String) -> CGFloat {
        let lines = max(1, text.split(separator: "\n", omittingEmptySubsequences: false).count)
        let wrapped = max(lines, Int(ceil(Double(text.count) / 52.0)))
        return min(300, max(44, CGFloat(wrapped) * 18 + 8))
    }

    private var header: some View {
        HStack(spacing: 8) {
            Image(systemName: "viewfinder")
                .font(.system(size: 13, weight: .semibold))
            Text("ScreenQuery")
                .font(.headline)
            Spacer()
            Button(action: onDismiss) {
                Image(systemName: "xmark")
                    .font(.system(size: 10, weight: .bold))
                    .frame(width: 22, height: 22)
                    .background(Color.white.opacity(0.14), in: Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Dismiss")
        }
    }

    private var footer: some View {
        HStack(spacing: 8) {
            if model.savedURL != nil {
                Button("Show", action: onReveal)
                    .buttonStyle(.bordered)
                    .controlSize(.small)
            }
            if model.llmText != nil {
                Button(model.copied ? "Copied" : "Copy", action: onCopy)
                    .buttonStyle(.bordered)
                    .controlSize(.small)
            }
            if let actionTitle = model.actionTitle {
                Button(actionTitle, action: onAction)
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
            }
            Spacer(minLength: 0)
            Text("Click to dismiss")
                .font(.caption2)
                .foregroundStyle(.white.opacity(0.62))
        }
    }
}
