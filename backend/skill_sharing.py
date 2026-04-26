#!/usr/bin/env python3
"""
skill_sharing.py - Export, import, and share skills.
Package skills for sharing with the community.
"""

import json
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from paths import SKILLS_PATH, LOGS_PATH

logger = logging.getLogger(__name__)

SHARING_DIR = LOGS_PATH / "skill_exports"


class SkillSharer:
    """Export and import skills for sharing."""

    def __init__(self):
        SHARING_DIR.mkdir(parents=True, exist_ok=True)

    def export_skill(
        self,
        skill_name: str,
        output_path: Optional[Path] = None,
        include_metadata: bool = True,
    ) -> Dict[str, Any]:
        """
        Export a skill to a shareable package.

        Creates a ZIP file containing:
        - skill.toml (the skill definition)
        - SKILL.md (if exists, documentation)
        - metadata.json (usage stats, version info)
        - scripts/ (if exists, any helper scripts)
        """
        skill_file = SKILLS_PATH / f"{skill_name}.toml"
        skill_dir = SKILLS_PATH / skill_name

        if not skill_file.exists() and not skill_dir.exists():
            return {"success": False, "error": f"Skill '{skill_name}' not found"}

        # Determine output path
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = SHARING_DIR / f"{skill_name}_{timestamp}.zip"
        else:
            output_path = Path(output_path)

        try:
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # Add skill.toml or skill directory
                if skill_dir.exists():
                    # Directory-style skill
                    for f in skill_dir.rglob("*"):
                        if f.is_file():
                            arcname = f"{skill_name}/{f.relative_to(skill_dir)}"
                            zf.write(f, arcname)
                else:
                    # Single file skill
                    zf.write(skill_file, f"{skill_name}.toml")

                    # Add SKILL.md if exists
                    skill_md = SKILLS_PATH / f"{skill_name}.md"
                    if skill_md.exists():
                        zf.write(skill_md, f"{skill_name}.md")

                    # Add scripts directory if exists
                    scripts_dir = SKILLS_PATH / "scripts" / skill_name
                    if scripts_dir.exists():
                        for f in scripts_dir.rglob("*"):
                            if f.is_file():
                                arcname = f"scripts/{f.relative_to(scripts_dir)}"
                                zf.write(f, arcname)

                # Add metadata
                if include_metadata:
                    metadata = self._generate_metadata(skill_name)
                    zf.writestr("metadata.json", json.dumps(metadata, indent=2))

            return {
                "success": True,
                "path": str(output_path),
                "size_bytes": output_path.stat().st_size,
                "skill": skill_name,
            }

        except Exception as e:
            logger.error(f"[Sharing] Export error: {e}")
            return {"success": False, "error": str(e)}

    def _generate_metadata(self, skill_name: str) -> Dict[str, Any]:
        """Generate metadata for a skill export."""
        from skill_analytics import get_skill_stats

        stats = get_skill_stats(skill_name)

        return {
            "skill_name": skill_name,
            "exported_at": datetime.now().isoformat(),
            "export_format_version": "1.0",
            "usage_stats": {
                "total_executions": stats.get("total_executions", 0),
                "success_rate": (
                    stats.get("successful_executions", 0) / stats.get("total_executions", 1)
                    if stats.get("total_executions", 0) > 0
                    else 0
                ),
            },
            "compatibility": {
                "min_version": "1.0.0",
                "platform": "windows",
            },
        }

    def import_skill(
        self,
        package_path: str | Path,
        dest_path: Optional[Path] = None,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """
        Import a skill from a shareable package.

        Validates the package and extracts to the skills directory.
        """
        package_path = Path(package_path)

        if not package_path.exists():
            return {"success": False, "error": "Package file not found"}

        if not zipfile.is_zipfile(package_path):
            return {"success": False, "error": "Invalid package format (not a ZIP file)"}

        if dest_path is None:
            dest_path = SKILLS_PATH

        try:
            with zipfile.ZipFile(package_path, "r") as zf:
                # Validate package contents
                file_list = zf.namelist()

                # Check for required files
                has_toml = any(f.endswith(".toml") for f in file_list)
                if not has_toml:
                    return {"success": False, "error": "Package missing skill.toml"}

                # Check metadata
                metadata = {}
                if "metadata.json" in file_list:
                    with zf.open("metadata.json") as f:
                        metadata = json.load(f)

                # Extract files
                extracted_files = []
                for member in file_list:
                    if member == "metadata.json":
                        continue

                    # Security: prevent path traversal
                    if ".." in member or member.startswith("/"):
                        logger.warning(f"[Sharing] Skipping suspicious path: {member}")
                        continue

                    target_path = dest_path / member

                    # Check for existing skill
                    if target_path.exists() and not overwrite:
                        return {
                            "success": False,
                            "error": f"File already exists: {target_path}",
                            "hint": "Use overwrite=True to replace",
                        }

                    # Extract
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as source:
                        with open(target_path, "wb") as target:
                            target.write(source.read())
                    extracted_files.append(str(target_path))

                # Reload skills
                try:
                    from skills import reload_skills_cache
                    reload_skills_cache()
                except ImportError:
                    pass

                return {
                    "success": True,
                    "extracted_files": extracted_files,
                    "metadata": metadata,
                    "skill_name": metadata.get("skill_name", "unknown"),
                }

        except Exception as e:
            logger.error(f"[Sharing] Import error: {e}")
            return {"success": False, "error": str(e)}

    def list_available_exports(self) -> List[Dict[str, Any]]:
        """List all exported skill packages."""
        exports = []

        for zip_file in SHARING_DIR.glob("*.zip"):
            try:
                with zipfile.ZipFile(zip_file, "r") as zf:
                    metadata_str = zf.read("metadata.json") if "metadata.json" in zf.namelist() else "{}"
                    metadata = json.loads(metadata_str)

                    exports.append({
                        "filename": zip_file.name,
                        "path": str(zip_file),
                        "size_bytes": zip_file.stat().st_size,
                        "exported_at": metadata.get("exported_at", "unknown"),
                        "skill_name": metadata.get("skill_name", "unknown"),
                    })
            except Exception as e:
                exports.append({
                    "filename": zip_file.name,
                    "path": str(zip_file),
                    "error": str(e),
                })

        return sorted(exports, key=lambda x: x.get("exported_at", ""), reverse=True)

    def share_to_community(
        self,
        skill_name: str,
        description: str,
        tags: List[str],
        author: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Prepare a skill for community sharing.

        Creates a shareable package with enhanced metadata.
        """
        # First export the skill
        export_result = self.export_skill(skill_name)

        if not export_result["success"]:
            return export_result

        # Create community metadata
        community_meta = {
            "skill_name": skill_name,
            "description": description,
            "tags": tags,
            "author": author or "anonymous",
            "shared_at": datetime.now().isoformat(),
            "package_path": export_result["path"],
        }

        # Save community metadata alongside the export
        meta_file = Path(export_result["path"]).with_suffix(".meta.json")
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(community_meta, f, indent=2)

        return {
            "success": True,
            "package": export_result["path"],
            "metadata_file": str(meta_file),
            "ready_to_share": True,
            "share_instructions": f"Share {export_result['path']} and {meta_file} with the community",
        }

    def validate_package(self, package_path: str | Path) -> Dict[str, Any]:
        """Validate a skill package without importing."""
        package_path = Path(package_path)

        if not package_path.exists():
            return {"valid": False, "error": "Package not found"}

        if not zipfile.is_zipfile(package_path):
            return {"valid": False, "error": "Not a valid ZIP file"}

        issues = []
        warnings = []

        try:
            with zipfile.ZipFile(package_path, "r") as zf:
                file_list = zf.namelist()

                # Required: skill.toml
                toml_files = [f for f in file_list if f.endswith(".toml")]
                if not toml_files:
                    issues.append("Missing skill.toml")

                # Check for potentially dangerous files
                for f in file_list:
                    if f.endswith(".exe") or f.endswith(".bat"):
                        warnings.append(f"Contains executable: {f}")
                    if f.startswith("/") or ".." in f:
                        issues.append(f"Unsafe path: {f}")

                # Check metadata
                if "metadata.json" in file_list:
                    try:
                        with zf.open("metadata.json") as mf:
                            meta = json.load(mf)
                            if "export_format_version" not in meta:
                                warnings.append("Missing export_format_version in metadata")
                    except Exception as e:
                        issues.append(f"Invalid metadata.json: {e}")

        except Exception as e:
            issues.append(f"Package error: {e}")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "files": [f for f in zipfile.ZipFile(package_path, "r").namelist() if not f.endswith("/")],
        }


# Global sharer instance
_sharer: Optional[SkillSharer] = None


def get_sharer() -> SkillSharer:
    """Get or create the global skill sharer."""
    global _sharer
    if _sharer is None:
        _sharer = SkillSharer()
    return _sharer


def export_skill(skill_name: str) -> Dict[str, Any]:
    """Export a skill for sharing."""
    return get_sharer().export_skill(skill_name)


def import_skill(package_path: str | Path, overwrite: bool = False) -> Dict[str, Any]:
    """Import a skill from a package."""
    return get_sharer().import_skill(package_path, overwrite=overwrite)


if __name__ == "__main__":
    # Test skill sharing
    logging.basicConfig(level=logging.INFO)

    print("Testing skill sharing...")

    sharer = get_sharer()

    # Export a skill
    print("\nExporting example_roll_dice skill...")
    result = sharer.export_skill("example_roll_dice")
    print(f"Export: {result}")

    # List exports
    print("\nAvailable exports:")
    for exp in sharer.list_available_exports():
        print(f"  {exp['skill_name']}: {exp['filename']}")

    # Validate package
    if result["success"]:
        print(f"\nValidating package...")
        validation = sharer.validate_package(result["path"])
        print(f"Valid: {validation['valid']}")
        if validation["warnings"]:
            print(f"Warnings: {validation['warnings']}")
