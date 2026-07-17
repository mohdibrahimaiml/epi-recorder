import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { COLORS, FONTS } from "../design/theme";
import { GlowText } from "../components/GlowText";

export const Scene3_Solution: React.FC = () => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();

    // Comparison rows data
    const rows = [
        { left: "📄 Document → PDF", right: "🧠 AI Execution → .epi" },
        { left: "Visual Fidelity", right: "Verifiable Execution" },
        { left: "Self-contained", right: "Self-contained" },
        { left: "Tamper-evident", right: "Cryptographically Signed" },
    ];

    // Slide in the comparison table
    const tableX = spring({
        fps,
        frame: frame - 10,
        from: -100,
        to: 0,
        config: { damping: 15 },
    });

    const tableOpacity = interpolate(frame, [10, 30], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
    });

    // Big tagline entrance
    const taglineFrame = 120;

    return (
        <AbsoluteFill
            style={{
                background: `linear-gradient(135deg, ${COLORS.bg} 0%, #0d1117 50%, ${COLORS.bg} 100%)`,
                justifyContent: "center",
                alignItems: "center",
            }}
        >
            <div
                style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: 50,
                    zIndex: 10,
                }}
            >
                {/* Comparison Table */}
                <div
                    style={{
                        opacity: tableOpacity,
                        transform: `translateX(${tableX}px)`,
                        display: "flex",
                        gap: 0,
                        borderRadius: 16,
                        overflow: "hidden",
                        border: `1px solid ${COLORS.borderLight}`,
                    }}
                >
                    {/* Left Column - PDF */}
                    <div
                        style={{
                            background: `${COLORS.bgCard}aa`,
                            padding: "32px 48px",
                            minWidth: 360,
                        }}
                    >
                        <div
                            style={{
                                fontSize: 14,
                                fontWeight: 700,
                                color: COLORS.textDim,
                                textTransform: "uppercase",
                                letterSpacing: 3,
                                marginBottom: 24,
                                fontFamily: FONTS.display,
                            }}
                        >
                            PDF Standard
                        </div>
                        {rows.map((row, i) => {
                            const rowOpacity = interpolate(frame, [20 + i * 12, 35 + i * 12], [0, 1], {
                                extrapolateLeft: "clamp",
                                extrapolateRight: "clamp",
                            });
                            return (
                                <div
                                    key={i}
                                    style={{
                                        opacity: rowOpacity,
                                        fontSize: 20,
                                        color: COLORS.textMuted,
                                        fontFamily: FONTS.display,
                                        fontWeight: 500,
                                        padding: "10px 0",
                                        borderBottom: i < rows.length - 1 ? `1px solid ${COLORS.borderLight}` : "none",
                                    }}
                                >
                                    {row.left}
                                </div>
                            );
                        })}
                    </div>

                    {/* Divider */}
                    <div style={{ width: 2, background: `linear-gradient(180deg, transparent, ${COLORS.primary}, transparent)` }} />

                    {/* Right Column - EPI */}
                    <div
                        style={{
                            background: `${COLORS.bgCard}`,
                            padding: "32px 48px",
                            minWidth: 360,
                        }}
                    >
                        <div
                            style={{
                                fontSize: 14,
                                fontWeight: 700,
                                color: COLORS.primary,
                                textTransform: "uppercase",
                                letterSpacing: 3,
                                marginBottom: 24,
                                fontFamily: FONTS.display,
                            }}
                        >
                            EPI Standard
                        </div>
                        {rows.map((row, i) => {
                            const rowOpacity = interpolate(frame, [25 + i * 12, 40 + i * 12], [0, 1], {
                                extrapolateLeft: "clamp",
                                extrapolateRight: "clamp",
                            });
                            return (
                                <div
                                    key={i}
                                    style={{
                                        opacity: rowOpacity,
                                        fontSize: 20,
                                        color: COLORS.text,
                                        fontFamily: FONTS.display,
                                        fontWeight: 600,
                                        padding: "10px 0",
                                        borderBottom: i < rows.length - 1 ? `1px solid ${COLORS.borderLight}` : "none",
                                    }}
                                >
                                    {row.right}
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Big Tagline */}
                <GlowText
                    text="The PDF for AI Evidence"
                    subtitle="Execution Proof Infrastructure"
                    startFrame={taglineFrame}
                    fontSize={64}
                    glowColor={COLORS.primary}
                />
            </div>
        </AbsoluteFill>
    );
};
