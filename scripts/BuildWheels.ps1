#
# Copyright 2021 GridGain Systems, Inc. and Contributors.
#
# Licensed under the GridGain Community Edition License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.gridgain.com/products/software/community-edition/gridgain-community-edition-license
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

$PyVers="39","310","311","312","313"

[System.Collections.ArrayList]$PyVersFull = $PyVers
foreach ($Ver in $PyVers)
{
	[Void]$PyVersFull.Add("$Ver-32")
}

foreach ($Ver in $PyVersFull)
{
	& "$env:LOCALAPPDATA\Programs\Python\Python$Ver\python.exe" -m venv epy$Ver
	
	. ".\epy$Ver\Scripts\Activate.ps1"
	pip install -e .
	pip install wheel
	pip wheel . --no-deps -w distr
}

