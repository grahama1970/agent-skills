# Kling Official Reference Notes

Last verified: 2026-06-11

These notes summarize the official Kling documentation used by this skill. Platform behavior can change, so re-check these links for production-critical work.

## Element Library

Source: `https://kling.ai/quickstart/klingai-element-library-3-user-guide`

Relevant points:

- Kling Element Library is intended to improve consistency for characters, props/items, and scenes.
- Multi-image Elements require at least 2 reference images: 1 main reference image plus 1 additional reference image.
- Multi-image Elements can include up to 4 reference images: 1 main reference image plus 3 supplementary reference images.
- For higher consistency, Kling recommends uploading a front-facing main reference image.
- Supplementary images can show different angles or additional details.
- Element descriptions should include the element’s core characteristics, key details, and features to ignore during generation.
- Supported Element types include characters, animals, props/items, costumes/accessories, scenes, special effects, and others.
- In Video 3.0, after uploading a frame or start/end frames, users can bind up to 3 additional elements; elements should appear in the reference frames to enhance consistency.
- In Video 3.0 Omni or Video O1, with video in the input area, users can upload a total of 4 images/elements; with no video, users can upload up to 7 images/elements.
- In Image 3.0 Omni or Image O1, users can upload up to 10 images/elements in total.

## VIDEO 3.0 Omni

Source: `https://kling.ai/quickstart/klingai-video-3-omni-model-user-guide`

Relevant points:

- Image uploads support `.jpg`, `.jpeg`, and `.png`.
- Images must have width and height of at least 300 px.
- Image file size must be 10 MB or less.
- Without video input, VIDEO 3.0 Omni can use up to 7 images/elements.
- With video input, VIDEO 3.0 Omni can use a total of up to 4 images/elements.
- Multi-perspective images up to 4 can be combined into one subject.
- Character subjects can use a 5–30 second single-person speech audio reference for voice binding.
- A 3–8 second single-character video clip can be used to create a video character element.

## VIDEO 3.0 Element Reference

Source: `https://kling.ai/quickstart/klingai-video-3-model-user-guide`

Relevant points:

- VIDEO 3.0 supports element binding to lock specific elements in the frame and improve subject consistency during camera movement.
- Binding can help maintain visual and audio consistency.
- Users can create Elements by uploading 2–4 reference images, and character Elements can include audio/voice tone.

## Image-to-Video Prompting

Source: `https://kling.ai/quickstart/image-to-video-guide`

Relevant points:

- Kling’s Image-to-Video guide frames prompting as: `Subject + Movement, Background + Movement`.
- Subject movement should be explicit, visible, and grounded.
- Background movement should be described when relevant.
- Vague commands are less reliable than explicit subject-action instructions.
