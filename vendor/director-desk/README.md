# 3D Director Desk in ComicFlow

ComicFlow builds and distributes the browser editor from [xiaozangao/3d-director-desk](https://github.com/xiaozangao/3d-director-desk/tree/a6c931cd36d8263d986706f74ab4efe9d5151959), version 0.3.1, under the upstream MIT license. The build pins the Git revision and uses its npm lockfile. The original author is YZ. The project is based on [jiguang132/storyai-3d-director-desk](https://github.com/jiguang132/storyai-3d-director-desk/tree/8c8bd36), also MIT.

The local build retains the editor, scene and camera tools, timeline, project format and host protocol. It uses the upstream procedural mannequin for built-in characters. The Sketchfab mannequin and the separate GUO and Mixamo model packs are excluded from the distributable assets. User-supplied model imports remain available. The build copies the upstream license and collects dependency notices with the editor.

Run `python -m scripts.build_director_desk` with Git, Node.js 24 and npm. To build from a checkout containing the pinned revision, pass `--source PATH`. Build outputs are placed in `assets/director_desk` and the trial builder packages them into the desktop ZIP. Users of the trial package do not need Git, Node.js or npm for the director desk.
