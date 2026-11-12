# python-for-android ships pygame 2.1.0, whose generated C code doesn't build with Python 3.11
# ("longintrepr.h not found"). pygame 2.1.3 fixed that.
# 2.1.3 also moved fast blitting into simd_blitters_sse2.c / simd_blitters_avx2.c, but its Android
# build file still lists the old sources for the surface module; on 64-bit phones (NEON on by default)
# surface.so then fails to load ("cannot locate symbol alphablit_alpha_sse2_argb_surf_alpha").
# So after the Setup file is written, the two SIMD files are added to the surface module.
from os.path import join
from pythonforandroid.recipes.pygame import Pygame2Recipe
from pythonforandroid.toolchain import current_directory


class PygameRecipe213(Pygame2Recipe):
    version = '2.1.3'

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)
        with current_directory(self.get_build_dir(arch.arch)):
            setup = open('Setup').read()
            old = 'surface src_c/surface.c'
            if 'simd_blitters_sse2.c' not in setup:
                if old not in setup:
                    raise Exception('pygame Setup: surface line not found')
                setup = setup.replace(old, 'surface src_c/simd_blitters_sse2.c src_c/simd_blitters_avx2.c src_c/surface.c', 1)
                open('Setup', 'w').write(setup)
            print('pygame Setup surface line:', [l for l in setup.splitlines() if l.startswith('surface ')])


recipe = PygameRecipe213()
