#!/usr/bin/env python3
"""
Robot controller for automated tape libraries
"""

import subprocess
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)

class RobotController:
    """Controller for tape library robots"""
    
    def __init__(self, robot_dev: str = "/dev/sg3"):
        self.robot_dev = robot_dev
        self.mtx_available = self._check_mtx_available()
        
        if self.mtx_available:
            logger.info(f"Robot controller initialized for device: {robot_dev}")
        else:
            logger.warning("mtx command not available, robot functions disabled")
    
    def _check_mtx_available(self) -> bool:
        """Check if mtx command is available"""
        try:
            result = subprocess.run(
                ["which", "mtx"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except:
            return False
    
    def run_mtx_command(self, command: str) -> Dict[str, Any]:
        """Execute mtx command and return result"""
        if not self.mtx_available:
            return {
                'success': False,
                'error': 'mtx command not available',
                'output': '',
                'error_output': ''
            }
        
        try:
            full_cmd = f"mtx -f {self.robot_dev} {command}"
            result = subprocess.run(
                full_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return {
                'success': result.returncode == 0,
                'output': result.stdout,
                'error_output': result.stderr,
                'return_code': result.returncode
            }
            
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout executing mtx command: {command}")
            return {
                'success': False,
                'error': 'Command timeout',
                'output': '',
                'error_output': 'Timeout expired'
            }
        except Exception as e:
            logger.error(f"Error executing mtx command {command}: {e}")
            return {
                'success': False,
                'error': str(e),
                'output': '',
                'error_output': str(e)
            }
    
    def get_status(self) -> Dict[str, Any]:
        """Get robot status"""
        result = self.run_mtx_command("status")
        
        status_info = {
            'available': self.mtx_available,
            'success': result['success'],
            'raw_output': result['output'],
            'slots': [],
            'drives': [],
            'import_export': []
        }
        
        if result['success'] and result['output']:
            # Parse mtx status output
            lines = result['output'].strip().split('\n')
            
            for line in lines:
                line = line.strip()
                
                # Parse storage slots
                if 'Storage Element' in line and 'Full' in line:
                    try:
                        # Example: "Storage Element 1:Full (Storage Element 1)"
                        parts = line.split(':')
                        if len(parts) >= 2:
                            slot_num = parts[0].split()[-1]
                            status = 'Full' if 'Full' in parts[1] else 'Empty'
                            status_info['slots'].append({
                                'slot': slot_num,
                                'status': status
                            })
                    except:
                        pass
                
                # Parse drives
                elif 'Data Transfer Element' in line:
                    try:
                        # Example: "Data Transfer Element 0:Full (Drive 0)"
                        parts = line.split(':')
                        if len(parts) >= 2:
                            drive_num = parts[0].split()[-1]
                            status = 'Full' if 'Full' in parts[1] else 'Empty'
                            status_info['drives'].append({
                                'drive': drive_num,
                                'status': status
                            })
                    except:
                        pass
        
        return status_info
    
    def load_tape(self, slot: int, drive: int = 0) -> bool:
        """Load tape from slot to drive"""
        result = self.run_mtx_command(f"load {slot} {drive}")
        
        if result['success']:
            logger.info(f"Loaded tape from slot {slot} to drive {drive}")
            return True
        else:
            logger.error(f"Failed to load tape from slot {slot}: {result.get('error_output', 'Unknown error')}")
            return False
    
    def unload_tape(self, drive: int = 0, slot: Optional[int] = None) -> bool:
        """Unload tape from drive to slot"""
        if slot is not None:
            result = self.run_mtx_command(f"unload {slot} {drive}")
        else:
            result = self.run_mtx_command(f"unload {drive}")
        
        if result['success']:
            logger.info(f"Unloaded tape from drive {drive}" + 
                       (f" to slot {slot}" if slot else ""))
            return True
        else:
            logger.error(f"Failed to unload tape from drive {drive}: {result.get('error_output', 'Unknown error')}")
            return False
    
    def transfer_tape(self, source_slot: int, dest_slot: int) -> bool:
        """Transfer tape between slots"""
        result = self.run_mtx_command(f"transfer {source_slot} {dest_slot}")
        
        if result['success']:
            logger.info(f"Transferred tape from slot {source_slot} to slot {dest_slot}")
            return True
        else:
            logger.error(f"Failed to transfer tape: {result.get('error_output', 'Unknown error')}")
            return False
    
    def load_cleaning_tape(self, cleaning_slot: int, drive: int = 0) -> bool:
        """Load cleaning tape"""
        result = self.run_mtx_command(f"load {cleaning_slot} {drive}")
        
        if result['success']:
            logger.info(f"Loaded cleaning tape from slot {cleaning_slot} to drive {drive}")
            return True
        else:
            logger.error(f"Failed to load cleaning tape: {result.get('error_output', 'Unknown error')}")
            return False
    
    def inventory(self) -> List[Dict[str, Any]]:
        """Get inventory of tapes in library"""
        status = self.get_status()
        
        if not status['success']:
            return []
        
        inventory = []
        
        # Parse slots
        for slot_info in status.get('slots', []):
            if slot_info['status'] == 'Full':
                inventory.append({
                    'type': 'tape',
                    'location': f"Slot {slot_info['slot']}",
                    'status': 'In slot'
                })
        
        # Parse drives
        for drive_info in status.get('drives', []):
            if drive_info['status'] == 'Full':
                inventory.append({
                    'type': 'tape',
                    'location': f"Drive {drive_info['drive']}",
                    'status': 'In drive'
                })
        
        return inventory
    
    def get_tape_positions(self) -> Dict[str, List[int]]:
        """Get current tape positions"""
        status = self.get_status()
        
        positions = {
            'loaded_drives': [],
            'filled_slots': [],
            'empty_slots': []
        }
        
        if status['success']:
            # Find loaded drives
            for drive_info in status.get('drives', []):
                if drive_info['status'] == 'Full':
                    positions['loaded_drives'].append(int(drive_info['drive']))
            
            # Find filled and empty slots
            for slot_info in status.get('slots', []):
                slot_num = int(slot_info['slot'])
                if slot_info['status'] == 'Full':
                    positions['filled_slots'].append(slot_num)
                else:
                    positions['empty_slots'].append(slot_num)
        
        return positions
    
    def is_operational(self) -> bool:
        """Check if robot is operational"""
        if not self.mtx_available:
            return False
        
        # Try to get status
        result = self.run_mtx_command("status")
        return result['success']
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get robot statistics"""
        return {
            'mtx_available': self.mtx_available,
            'device': self.robot_dev,
            'operational': self.is_operational(),
            'inventory_count': len(self.inventory())
        }