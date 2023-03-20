import os
import sys
import subprocess
import time
import libvirt


# Define common variables
num_vms = 2
vm_name_prefix = "react-vm"
bridge_name = "virbr1"
storage_pool_name = "vmpool"
vm_image_path = "/var/lib/libvirt/images"
vm_xml_template = """<domain type='kvm'>
  <name>{vm_name}</name>
  <memory unit='GB'>64</memory>
  <vcpu placement='static'>32</vcpu>
  <os>
    <type arch='x86_64' machine='pc-q35-rhel8.6.0'>hvm</type>
    <boot dev='hd'/>
  </os>
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='/var/lib/libvirt/images/{vm_name}.qcow2'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <interface type='bridge'>
      <mac address='{mac_address}'/>
      <source bridge='{bridge_name}'/>
      <model type='virtio'/>
    </interface>
  </devices>
</domain>"""


baseos_file = '/root/fast-baseos/baseos-rockyos.qcow2'
simple_baseos_file = '/root/fast-baseos/fast-baseos.qcow2'

if not os.path.isfile(baseos_file):
    print(f"Error: fast-BaseOS file {baseos_file} does not exist.")
    exit()
os.system(f"cp {baseos_file} {simple_baseos_file}")

def create_all():

  # Connect to the KVM hypervisor
  try:
      
  ################################################

      print("\n ********  Stage: Storage pool for VM images ********\n")
      
      pool_xml = f"""<pool type='dir'>
        <name>{storage_pool_name}</name>
        <target>
          <path>{vm_image_path}</path>
        </target>
      </pool>"""

      try:
          poolobj = conn.storagePoolLookupByName(storage_pool_name)
      except Exception as ex:
          if ex.get_error_code() == libvirt.VIR_ERR_NO_STORAGE_POOL:  # checking.. if pool does not exist, then create..
              print(f"The {storage_pool_name} storage pool does not exist.\n Hence creating now...\n")
              pool = conn.storagePoolDefineXML(pool_xml, 0)
              pool.create()
          else:
              raise
      if poolobj is not None:
          print(f"The storage pool named {storage_pool_name} already exists.\n Destrying and Recreating now...\n")
          command = f"sudo virsh pool-destroy {storage_pool_name} ; sudo virsh pool-undefine {storage_pool_name}\n"
          output = subprocess.run(command, shell=True, check=True)
          print(output)
          pool = conn.storagePoolDefineXML(pool_xml, 0)
          pool.create()
      pools=conn.listStoragePools()
      print(f"Storage pool created: {pools}\n")


      ############################################################


      print("\n ********* Stage: Bridge network for VM ********* \n")
      print("Checking if virbr1 Bridge alreay exists..")

      network_xml = f"""<network>
        <name>{bridge_name}</name>
        <bridge name='{bridge_name}'/>
        <ip address='192.168.100.1' netmask='255.255.255.0'>
          <dhcp>
            <range start='192.168.100.2' end='192.168.100.254'/>
          </dhcp>
        </ip>
      </network>"""

      try:
          command = f"sudo virsh net-destroy {bridge_name} ; sudo virsh net-undefine {bridge_name}"
          output = subprocess.run(command, shell=True, check=True)
          print(output)
          network = conn.networkDefineXML(network_xml)
          network.create()
      except Exception as ex:
          print(f"{bridge_name} does not exist. Moving ahead with {bridge_name} creation. \n")
          network = conn.networkDefineXML(network_xml)
          network.create()
      command = "sudo brctl show"
      output = subprocess.run(command, shell=True, check=True)
      print(output)

      ########################################################################

      print("\n********* Create the VMs  ********* \n")

      for i in range(num_vms):
          vm_name = f"{vm_name_prefix}{i}"
          print(f"***Working on Compute VM : {vm_name}*** \n")

          # Generate VM name and MAC address
          mac_address = "52:54:00:" + ":".join([f"{x:02x}" for x in os.urandom(3)])
          # Create the VM image
          image_path = f"{vm_image_path}/{vm_name}.qcow2"

          #os.system(f"qemu-img create -f qcow2 -b {simple_baseos_file} {image_path} 10G")
          #qemu-img create -f qcow2 -o preallocation=metadata /tmp/test_image.qcow2 10G
          os.system(f"cp {simple_baseos_file} {image_path}")

          # Create the VM XML definition
          vm_xml = vm_xml_template.format(
              vm_name=vm_name,
              mac_address=mac_address,
              bridge_name=bridge_name,
              vm_image_path=vm_image_path,
          )
          try:
                print(f"\nChecking if {vm_name} exists...")
                command = f"sudo virsh destroy {vm_name} ; sudo virsh undefine {vm_name}"
                output = subprocess.run(command, shell=True, check=True)
                print(output)
                # Define and start the VM
                vm = conn.defineXML(vm_xml)
                vm.create()
                command = "sudo virsh list"
                output = subprocess.run(command, shell=True, check=True)
                print(output)
          except Exception as ex:
                print(f"\n{vm_name} does not exist. Hence moving ahead with {vm_name} creation.\n")
                # Define and start the VM
                vm = conn.defineXML(vm_xml)
                vm.create()
                command = "sudo virsh list"
                output = subprocess.run(command, shell=True, check=True)
                print(output)

  except Exception as ex:
      print(f"\n Entered Exception loop. \n An error occurred: {ex}")
      print("Cleaning up resources...")

      # Deleting the failed VMs and its remanants.
      try:
        delete_all(num_vms, vm_image_path, bridge_name, storage_pool_name)
      except Exception as ex:
          print(f"Failed to delete components for VM {vm_name}")

def delete_all(num_vms, vm_image_path, bridge_name, storage_pool_name):
    for i in range(num_vms):
        vm_name = f"{vm_name_prefix}{i}"
        os.system(f"virsh destroy {vm_name}")
        os.system(f"virsh undefine {vm_name}")
        vm_qcow2_path = f"{vm_image_path}/{vm_name}.qcow2"
        os.remove(vm_qcow2_path)
    os.system(f"virsh net-destroy {bridge_name}")
    os.system(f"virsh net-undefine {bridge_name}")
    os.system(f"virsh pool-destroy {storage_pool_name}")
    os.system(f"virsh pool-undefine {storage_pool_name}")
    # Closing KVM hypervisor connection


if __name__ == '__main__':
    
    conn = libvirt.open()
    
    action = sys.argv[1]
    
    if action == 'create':
        create_all()
    elif action == 'delete':
        delete_all(num_vms, vm_image_path, bridge_name, storage_pool_name)
    else:
        print('Invaling argument')
        sys.exit(1)
    
    time.sleep(3)
    conn.close()
