import * as vscode from 'vscode';

export function activate(context: vscode.ExtensionContext): void {
    context.subscriptions.push(
        vscode.languages.registerFoldingRangeProvider(
            { language: 'archml' },
            new ArchmlFoldingRangeProvider()
        )
    );
}

export function deactivate(): void {}

// ################
// Implementation
// ################

class ArchmlFoldingRangeProvider implements vscode.FoldingRangeProvider {
    provideFoldingRanges(
        document: vscode.TextDocument,
        _context: vscode.FoldingContext,
        _token: vscode.CancellationToken
    ): vscode.FoldingRange[] {
        const ranges: vscode.FoldingRange[] = [];

        ranges.push(...this._descriptionRanges(document));
        ranges.push(...this._braceRanges(document));

        return ranges;
    }

    /**
     * Find folding ranges for triple-quoted description strings.
     *
     * A line with an odd number of `"""` occurrences toggles open/close state.
     * Single-line descriptions (`"""text"""`) have an even count and are skipped.
     */
    private _descriptionRanges(document: vscode.TextDocument): vscode.FoldingRange[] {
        const ranges: vscode.FoldingRange[] = [];
        let startLine: number | undefined;

        for (let i = 0; i < document.lineCount; i++) {
            const text = document.lineAt(i).text;
            const count = _countTripleQuotes(text);

            if (count % 2 === 1) {
                if (startLine === undefined) {
                    startLine = i;
                } else {
                    if (i > startLine) {
                        ranges.push(new vscode.FoldingRange(
                            startLine,
                            i,
                            vscode.FoldingRangeKind.Comment
                        ));
                    }
                    startLine = undefined;
                }
            }
        }

        return ranges;
    }

    /**
     * Find folding ranges for `{ }` entity bodies.
     *
     * VSCode's built-in bracket folding handles this when `brackets` is set in
     * language-configuration.json, but providing it here as well ensures it works
     * even when the built-in provider is unavailable (e.g. in embedded contexts).
     */
    private _braceRanges(document: vscode.TextDocument): vscode.FoldingRange[] {
        const ranges: vscode.FoldingRange[] = [];
        const stack: number[] = [];

        for (let i = 0; i < document.lineCount; i++) {
            const text = document.lineAt(i).text;

            // Skip lines inside a triple-quoted string by checking for odd-quote
            // toggle state — handled separately; here we just track braces.
            for (const ch of text) {
                if (ch === '{') {
                    stack.push(i);
                } else if (ch === '}') {
                    const openLine = stack.pop();
                    if (openLine !== undefined && i > openLine) {
                        ranges.push(new vscode.FoldingRange(openLine, i));
                    }
                }
            }
        }

        return ranges;
    }
}

function _countTripleQuotes(line: string): number {
    let count = 0;
    let pos = 0;
    while ((pos = line.indexOf('"""', pos)) !== -1) {
        count++;
        pos += 3;
    }
    return count;
}
