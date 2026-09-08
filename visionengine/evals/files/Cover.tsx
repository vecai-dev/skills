import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";

export const Cover: React.FC<{ title?: string }> = ({ title = "VisionEngine" }) => {
  return (
    <AbsoluteFill
      style={{
        alignItems: "center",
        backgroundColor: "#0b1020",
        color: "#ffffff",
        display: "flex",
        justifyContent: "center",
      }}
    >
      <Img src={staticFile("images/cover.png")} style={{ borderRadius: 24, width: 720 }} />
      <h1 style={{ fontFamily: "sans-serif", fontSize: 96, marginTop: 48 }}>{title}</h1>
    </AbsoluteFill>
  );
};
