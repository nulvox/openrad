{
  description = "openrad dev environment";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems f;
    in
    {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        {
          default = pkgs.mkShell {
            # ruff comes from nixpkgs, not uv: it's a standalone native
            # binary, and manylinux wheels of it won't execute on NixOS
            # (foreign ELF interpreter) without nix-ld. mypy/pytest are
            # fine via `uv run` since they execute through the (correctly
            # linked) venv's Python instead of running as bare binaries.
            packages = [ pkgs.uv pkgs.python312 pkgs.ruff ];

            # NixOS doesn't ship libstdc++/libz in the standard dynamic
            # linker path, but manylinux wheels (numpy, matplotlib, ...)
            # installed by uv expect them there. Point the loader at
            # nixpkgs' copies instead of vendoring/patching the wheels.
            LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
              pkgs.stdenv.cc.cc.lib
              pkgs.zlib
            ];

            shellHook = ''
              echo "openrad dev shell — uv $(uv --version)"
            '';
          };
        });
    };
}
