# Read iPhone photos (HEIC) of bills

Uploads accept HEIC/HEIF photos (`storage.sniff` recognises their brands), but the bill reader opens
images with Pillow, which cannot decode HEIC without `pillow-heif`. Such a photo comes back with
nothing read and no message saying why.

- Add `pillow-heif` (a version at least 14 days old) and register its opener before
  `extraction.pipeline` opens images.
- Test with a synthetic HEIC (pillow-heif can write one), and check the image's size impact.
- Until then, say so: a HEIC upload to "Upload a bill" could answer "Photos from an iPhone cannot
  be read yet; enter the bill by hand", rather than an empty form.
