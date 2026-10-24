@description('Existing Container Apps environment resource ID; this template does not create it.')
param environmentId string
param location string = resourceGroup().location
@description('Immutable collector image tag or digest built from this source.')
param image string
@description('Existing user-assigned identity with Key Vault secret access and any required registry pull permission.')
param identityResourceId string
param krogerClientIdSecretUrl string
param krogerClientSecretUrl string
param storageConnectionSecretUrl string
param jobName string = 'marianos-westloop-api-trial'
param storeId string = '53100508'
param zipcode string = '60661'
param blobContainer string = 'marianos-api-trials'
@description('Keep manual until an actual Azure execution is reviewed. Schedule: Mon/Thu 06:00 UTC.')
param enableSchedule bool = false
param registryServer string = ''

resource job 'Microsoft.App/jobs@2024-03-01' = {
  name: jobName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityResourceId}': {}
    }
  }
  properties: {
    environmentId: environmentId
    configuration: union({
      replicaTimeout: 3600
      replicaRetryLimit: 0
      secrets: [
        { name: 'kroger-client-id'
          keyVaultUrl: krogerClientIdSecretUrl
          identity: identityResourceId }
        { name: 'kroger-client-secret'
          keyVaultUrl: krogerClientSecretUrl
          identity: identityResourceId }
        { name: 'blob-connection'
          keyVaultUrl: storageConnectionSecretUrl
          identity: identityResourceId }
      ]
      registries: empty(registryServer) ? [] : [
        { server: registryServer
          identity: identityResourceId }
      ]
    }, enableSchedule ? {
      triggerType: 'Schedule'
      scheduleTriggerConfig: { cronExpression: '0 6 * * 1,4'
          parallelism: 1
          replicaCompletionCount: 1 }
    } : {
      triggerType: 'Manual'
      manualTriggerConfig: { parallelism: 1
          replicaCompletionCount: 1 }
    })
    template: {
      containers: [
        {
          name: 'collector'
          image: image
          resources: { cpu: json('0.5')
          memory: '1Gi' }
          env: [
            { name: 'MARIANOS_MODE'
          value: 'api-trial' }
            { name: 'MARIANOS_STORE_ID'
          value: storeId }
            { name: 'MARIANOS_ZIPCODE'
          value: zipcode }
            { name: 'AZURE_BLOB_CONTAINER'
          value: blobContainer }
            { name: 'KROGER_CLIENT_ID'
          secretRef: 'kroger-client-id' }
            { name: 'KROGER_CLIENT_SECRET'
          secretRef: 'kroger-client-secret' }
            { name: 'AZURE_STORAGE_CONNECTION_STRING'
          secretRef: 'blob-connection' }
          ]
        }
      ]
    }
  }
}
output jobResourceId string = job.id

