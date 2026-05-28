import fs from "node:fs/promises";
import path from "node:path";
import {
  Presentation,
  PresentationFile,
  column,
  row,
  text,
  shape,
  fill,
  hug,
  fixed,
} from "file:///C:/Users/Munawara Kazmi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";

const WORKSPACE = path.resolve("tmp/presentations/hmi-ecu");
const SCRATCH = path.join(WORKSPACE, "scratch");
const OUTPUT = path.join(WORKSPACE, "output");
const PPTX_PATH = path.join(OUTPUT, "output.pptx");

const COLORS = {
  bg: "#FFFFFF",
  title: "#0A2B59",
  teal: "#0A9B93",
  body: "#3D4F64",
  muted: "#7F8EA0",
  placeholderLine: "#C7D2DD",
  placeholderFill: "#FAFCFD",
};

function infoBlock(label, body) {
  return column(
    {
      width: fill,
      height: hug,
      gap: 8,
    },
    [
      text(label, {
        width: fill,
        height: hug,
        style: {
          fontSize: 22,
          bold: true,
          color: COLORS.title,
        },
      }),
      text(body, {
        width: fill,
        height: hug,
        style: {
          fontSize: 18,
          color: COLORS.body,
          breakLine: false,
        },
      }),
    ],
  );
}

function addTemplateChrome(slide, pageNumber) {
  slide.background.fill = { type: "solid", color: COLORS.bg };

  slide.shapes.add({
    geometry: "ellipse",
    position: { left: 78, top: 72, width: 18, height: 108 },
    fill: { type: "solid", color: COLORS.teal },
  });

  slide.compose(
    text(String(pageNumber), {
      name: `page-${pageNumber}`,
      width: fixed(26),
      height: hug,
      style: {
        fontSize: 16,
        color: COLORS.title,
      },
    }),
    {
      frame: { left: 1848, top: 1016, width: 26, height: 24 },
      baseUnit: 8,
    },
  );
}

function addSlideTitle(slide, titleText) {
  slide.compose(
    text(titleText, {
      name: `${titleText.toLowerCase().replace(/\s+/g, "-")}-title`,
      width: fill,
      height: hug,
      style: {
        fontSize: 54,
        bold: true,
        color: COLORS.title,
      },
    }),
    {
      frame: { left: 112, top: 68, width: 640, height: 72 },
      baseUnit: 8,
    },
  );
}

function addSpeakerNotes(slide, notes) {
  slide.speakerNotes.setText(notes);
  slide.speakerNotes.setVisible(true);
}

function buildSlideOne(presentation) {
  const slide = presentation.slides.add();
  addTemplateChrome(slide, 1);
  addSlideTitle(slide, "HMI ECU");

  slide.compose(
    row(
      {
        name: "slide-1-main-row",
        width: fill,
        height: fill,
        gap: 72,
      },
      [
        column(
          {
            name: "slide-1-left",
            width: fixed(650),
            height: fill,
            gap: 26,
          },
          [
            text("SOFTWARE BUILD", {
              name: "slide-1-kicker",
              width: fill,
              height: hug,
              style: {
                fontSize: 18,
                bold: true,
                color: COLORS.teal,
              },
            }),
            infoBlock(
              "Tabbed cluster flow",
              "Overview, Drive, Battery, Inverter, Odometer, and Faults views were separated so the main screen stays readable while deeper service information remains immediately accessible.",
            ),
            infoBlock(
              "Live data backend",
              "USB and serial services feed a shared state store; protocol parsing, stale-data handling, and safe zero fallbacks keep the interface predictable during subsystem bring-up.",
            ),
            infoBlock(
              "Pack-level diagnostics",
              "The Neuwat RS-485 integration now surfaces online packs, separate SoC values, and cleaned pack data directly in the HMI, making comparison and fault isolation much faster.",
            ),
            infoBlock(
              "Deployment-ready structure",
              "The app was split into UI, parsers, services, and launch scripts so features could be developed incrementally and moved to hardware without rewriting the whole stack.",
            ),
          ],
        ),
        column(
          {
            name: "slide-1-right",
            width: fill,
            height: fill,
            gap: 16,
          },
          [
            text("Space reserved for final dashboard screenshots", {
              name: "slide-1-placeholder-caption",
              width: fill,
              height: hug,
              style: {
                fontSize: 18,
                color: COLORS.muted,
              },
            }),
            shape({
              name: "slide-1-placeholder",
              geometry: "roundRect",
              width: fill,
              height: fixed(560),
              fill: { type: "solid", color: COLORS.placeholderFill },
              line: { style: "solid", fill: COLORS.placeholderLine, width: 2 },
            }),
            text("Use this area for the frozen overview, drive, and faults screens once the final vehicle visuals are captured.", {
              name: "slide-1-placeholder-note",
              width: fill,
              height: hug,
              style: {
                fontSize: 16,
                color: COLORS.muted,
              },
            }),
          ],
        ),
      ],
    ),
    {
      frame: { left: 112, top: 196, width: 1696, height: 734 },
      baseUnit: 8,
    },
  );

  addSpeakerNotes(
    slide,
    [
      "This slide should be presented as the software depth story behind the HMI, not just the visual outcome.",
      "Emphasize that the architecture was built to reduce diagnostic time during integration: a fast overview for system status, deeper pages for subsystem detail, and pack-level battery visibility directly inside the dashboard.",
      "Also point out that the modular Python structure kept the development loop affordable and practical because parsing, UI work, and deployment could advance independently before every hardware interface was finalized.",
    ].join("\n\n"),
  );

  return slide;
}

function buildSlideTwo(presentation) {
  const slide = presentation.slides.add();
  addTemplateChrome(slide, 2);
  addSlideTitle(slide, "HMI ECU");

  slide.compose(
    row(
      {
        name: "slide-2-main-row",
        width: fill,
        height: fill,
        gap: 78,
      },
      [
        column(
          {
            name: "slide-2-left",
            width: fixed(790),
            height: fill,
            gap: 16,
          },
          [
            text("Space reserved for hardware and battery-page captures", {
              name: "slide-2-placeholder-caption",
              width: fill,
              height: hug,
              style: {
                fontSize: 18,
                color: COLORS.muted,
              },
            }),
            shape({
              name: "slide-2-placeholder",
              geometry: "roundRect",
              width: fill,
              height: fixed(560),
              fill: { type: "solid", color: COLORS.placeholderFill },
              line: { style: "solid", fill: COLORS.placeholderLine, width: 2 },
            }),
            text("This space can hold the installed hardware view, touch interaction, or a final battery diagnostics screen capture.", {
              name: "slide-2-placeholder-note",
              width: fill,
              height: hug,
              style: {
                fontSize: 16,
                color: COLORS.muted,
              },
            }),
          ],
        ),
        column(
          {
            name: "slide-2-right",
            width: fill,
            height: fill,
            gap: 26,
          },
          [
            text("HARDWARE DEPLOYMENT", {
              name: "slide-2-kicker",
              width: fill,
              height: hug,
              style: {
                fontSize: 18,
                bold: true,
                color: COLORS.teal,
              },
            }),
            infoBlock(
              "Raspberry Pi 4 as the HMI controller",
              "It provides enough graphics headroom for a fullscreen Python interface while still supporting USB, serial, remote access, and repeatable deployment on widely available hardware.",
            ),
            infoBlock(
              "7-inch capacitive touch screen",
              "The touch panel fits the app's tabbed interaction model well and supports future service menus, pack inspection pages, and setup actions without requiring extra input hardware.",
            ),
            infoBlock(
              "Bench-to-vehicle workflow",
              "The same software stack can be tested manually during integration and then moved to boot-time launch, which shortens iteration time and keeps the hardware/software path easy to reproduce.",
            ),
            infoBlock(
              "Why this pairing works",
              "Together, the Pi 4 and touch display offer a practical balance between interactivity, deployment simplicity, and low overhead for both hardware replacement and software iteration.",
            ),
          ],
        ),
      ],
    ),
    {
      frame: { left: 112, top: 196, width: 1696, height: 734 },
      baseUnit: 8,
    },
  );

  addSpeakerNotes(
    slide,
    [
      "Present this slide as the reason the HMI can move from development bench to vehicle without a major tooling jump.",
      "Stress that Raspberry Pi 4 and the 7-inch capacitive touch screen were selected because they support interactive diagnostics cleanly while avoiding the cost and inflexibility of more specialized display hardware.",
      "The important message is not just that the hardware works, but that it keeps both the development process and future maintenance practical.",
    ].join("\n\n"),
  );

  return slide;
}

async function saveBlob(blob, filePath) {
  let bytes;
  if (blob && typeof blob.arrayBuffer === "function") {
    bytes = new Uint8Array(await blob.arrayBuffer());
  } else if (blob && blob.data instanceof Uint8Array) {
    bytes = blob.data;
  } else if (blob && ArrayBuffer.isView(blob.data)) {
    bytes = new Uint8Array(blob.data.buffer, blob.data.byteOffset, blob.data.byteLength);
  } else if (blob instanceof Uint8Array) {
    bytes = blob;
  } else {
    throw new TypeError("Unsupported export payload while saving file.");
  }
  await fs.writeFile(filePath, bytes);
}

async function exportLayouts(slides) {
  for (let index = 0; index < slides.length; index += 1) {
    const layout = await slides[index].export({ format: "layout" });
    const filePath = path.join(
      SCRATCH,
      `slide-${String(index + 1).padStart(2, "0")}-layout.json`,
    );
    await fs.writeFile(filePath, `${JSON.stringify(layout, null, 2)}\n`, "utf8");
  }
}

async function exportSourcePreviews(slides) {
  for (let index = 0; index < slides.length; index += 1) {
    const png = await slides[index].export({ format: "png" });
    const filePath = path.join(
      SCRATCH,
      `slide-${String(index + 1).padStart(2, "0")}-source.png`,
    );
    await saveBlob(png, filePath);
  }
}

async function exportPptxPreviews(presentation) {
  for (let index = 0; index < presentation.slides.count; index += 1) {
    const slide = presentation.slides.getItem(index);
    const png = await slide.export({ format: "png" });
    const filePath = path.join(
      SCRATCH,
      `slide-${String(index + 1).padStart(2, "0")}-pptx.png`,
    );
    await saveBlob(png, filePath);
  }
}

async function main() {
  await fs.mkdir(SCRATCH, { recursive: true });
  await fs.mkdir(OUTPUT, { recursive: true });

  const presentation = Presentation.create({
    slideSize: { width: 1920, height: 1080 },
  });

  const slides = [buildSlideOne(presentation), buildSlideTwo(presentation)];

  await exportLayouts(slides);
  await exportSourcePreviews(slides);

  const pptxBlob = await PresentationFile.exportPptx(presentation);
  await saveBlob(pptxBlob, PPTX_PATH);

  const imported = await PresentationFile.importPptx(await fs.readFile(PPTX_PATH));
  await exportPptxPreviews(imported);

  const notesCheck = [];
  for (let index = 0; index < imported.slides.count; index += 1) {
    const slide = imported.slides.getItem(index);
    notesCheck.push({
      slide: index + 1,
      notes: slide.speakerNotes.text,
    });
  }
  await fs.writeFile(
    path.join(SCRATCH, "speaker-notes-check.json"),
    `${JSON.stringify(notesCheck, null, 2)}\n`,
    "utf8",
  );

  console.log(
    JSON.stringify(
      {
        pptx: PPTX_PATH,
        sourcePreviews: [
          path.join(SCRATCH, "slide-01-source.png"),
          path.join(SCRATCH, "slide-02-source.png"),
        ],
        pptxPreviews: [
          path.join(SCRATCH, "slide-01-pptx.png"),
          path.join(SCRATCH, "slide-02-pptx.png"),
        ],
      },
      null,
      2,
    ),
  );
}

await main();
