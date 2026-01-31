"""
Setup configuration for post-install hook
This runs automatically after pip install
"""
from setuptools import setup
from setuptools.command.install import install
import subprocess
import sys


class PostInstallCommand(install):
    """Post-installation command to fix PATH issues"""
    
    def run(self):
        # Run the standard install
        install.run(self)
        
        # Run our post-install script
        try:
            subprocess.run(
                [sys.executable, '-m', 'epi_postinstall'],
                check=False  # Don't fail if post-install has issues
            )
        except Exception as e:
            print(f"Post-install check skipped: {e}")


# This is used if building with setup.py instead of just pyproject.toml
if __name__ == "__main__":
    setup(
        cmdclass={
            'install': PostInstallCommand,
        },
    )


