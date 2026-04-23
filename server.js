const path = require("path");
const express = require("express");
const multer = require("multer");
const tf = require("@tensorflow/tfjs-node");
const cocoSsd = require("@tensorflow-models/coco-ssd");

const app = express();
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 10 * 1024 * 1024 },
});

const PORT = process.env.PORT || 3000;

let modelPromise = null;

function loadModel() {
  if (!modelPromise) {
    modelPromise = cocoSsd.load({ base: "lite_mobilenet_v2" });
  }
  return modelPromise;
}

function broadLabel(label) {
  const value = String(label || "").toLowerCase();
  const map = {
    dog: "Dog",
    cat: "Cat",
    cow: "Cow",
    horse: "Horse",
    elephant: "Elephant",
    bird: "Crow",
    crow: "Crow",
    kite: "Kite",
    pigeon: "Pigeon",
    sparrow: "Sparrow",
    parrot: "Parrot",
    duck: "Duck",
    sheep: "Sheep",
    goat: "Goat",
    bear: "Bear",
    zebra: "Zebra",
    giraffe: "Giraffe",
    lion: "Lion",
    tiger: "Tiger",
  };

  return map[value] || label || "Unknown";
}

app.use(express.static(__dirname));

app.get("/api/health", (_req, res) => {
  res.json({ ok: true });
});

app.post("/api/recognize", upload.single("image"), async (req, res) => {
  try {
    if (!req.file || !req.file.buffer) {
      return res.status(400).send("No image uploaded.");
    }

    const model = await loadModel();
    const imageTensor = tf.node.decodeImage(req.file.buffer, 3);
    let predictions = [];
    try {
      predictions = await model.detect(imageTensor);
    } finally {
      imageTensor.dispose();
    }

    const chosen = predictions[0];
    const detected = chosen ? broadLabel(chosen.class) : "Unknown";
    const confidence = chosen && typeof chosen.score === "number" ? chosen.score : 0;
    const alternatives = predictions.slice(1, 4).map((item) => ({
      name: broadLabel(item.class),
      confidence: item.score || 0,
    }));

    const response = {
      detected,
      confidence,
      alternatives,
      note: chosen && String(chosen.class || "").toLowerCase() === "bird"
        ? "Bird detected. Use the Dex to confirm the exact bird."
        : "Server-side recognition complete. Tap the closest Dex match to confirm.",
    };

    return res.json(response);
  } catch (error) {
    return res.status(500).send(error && error.message ? error.message : "Recognition failed.");
  }
});

app.get("*", (_req, res) => {
  res.sendFile(path.join(__dirname, "index.html"));
});

app.listen(PORT, () => {
  console.log(`Anidex server running on http://127.0.0.1:${PORT}`);
});
